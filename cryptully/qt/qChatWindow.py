import os
import signal
import sys

from PyQt4.QtCore import pyqtSignal
from PyQt4.QtCore import pyqtSlot
from PyQt4.QtCore import Qt
from PyQt4.QtGui import QFontMetrics
from PyQt4.QtGui import QAction
from PyQt4.QtGui import QIcon
from PyQt4.QtGui import QInputDialog
from PyQt4.QtGui import QLabel
from PyQt4.QtGui import QMainWindow
from PyQt4.QtGui import QMenu
from PyQt4.QtGui import QMessageBox
from PyQt4.QtGui import QPushButton
from PyQt4.QtGui import QSplitter
from PyQt4.QtGui import QSystemTrayIcon
from PyQt4.QtGui import QTabWidget
from PyQt4.QtGui import QTextEdit
from PyQt4.QtGui import QToolBar
from PyQt4.QtGui import QToolButton
from PyQt4.QtGui import QVBoxLayout
from PyQt4.QtGui import QWidget

from qChatTab import QChatTab
from qAcceptDialog import QAcceptDialog
from qHelpDialog import QHelpDialog
import qtUtils

from utils import constants
from utils import errors
from utils import utils


class QChatWindow(QMainWindow):
    newClientSignal = pyqtSignal(str)
    clientReadySignal = pyqtSignal(str)
    handleErrorSignal = pyqtSignal(str, int)
    sendMessageToTabSignal = pyqtSignal(str, str, str)

    def __init__(self, restartCallback, connectionManager=None, messageQueue=None):
        QMainWindow.__init__(self)

        self.restartCallback = restartCallback
        self.connectionManager = connectionManager
        self.messageQueue = messageQueue
        self.newClientSignal.connect(self.newClientSlot)
        self.clientReadySignal.connect(self.clientReadySlot)
        self.handleErrorSignal.connect(self.handleErrorSlot)
        self.sendMessageToTabSignal.connect(self.sendMessageToTab)

        self.chatTabs = QTabWidget(self)
        self.chatTabs.setTabsClosable(True)
        self.chatTabs.setMovable(True)
        self.chatTabs.tabCloseRequested.connect(self.closeTab)
        self.chatTabs.currentChanged.connect(self.tabChanged)

        self.statusBar = self.statusBar()
        self.systemTrayIcon = QSystemTrayIcon(self)
        self.systemTrayIcon.setVisible(True)

        self.__setMenubar()

        vbox = QVBoxLayout()
        vbox.addWidget(self.chatTabs)

        # Add the completeted layout to the window
        self.centralWidget = QWidget()
        self.centralWidget.setLayout(vbox)
        self.setCentralWidget(self.centralWidget)

        qtUtils.resizeWindow(self, 700, 400)
        qtUtils.centerWindow(self)

        # Title and icon
        self.setWindowTitle("Cryptully")
        self.setWindowIcon(QIcon(qtUtils.getAbsoluteImagePath('icon.png')))


    def connectedToServer(self):
        # Add an initial tab once connected to the server
        self.addNewTab()


    def newClient(self, nick):
        # This function is called from a bg thread. Send a signal to get on the UI thread
        self.newClientSignal.emit(nick)


    @pyqtSlot(str)
    def newClientSlot(self, nick):
        nick = str(nick)

        # Show a system notifcation of the new client if not the current window
        if not self.isActiveWindow():
            qtUtils.showDesktopNotification(self.systemTrayIcon, "Chat request from " + nick, '')

        # Show the accept dialog
        accept = QAcceptDialog.getAnswer(self, nick)

        if not accept:
            self.connectionManager.newClientRejected(nick)
            return

        # If nick already has a tab, reuse it
        if self.isNickInTabs(nick):
            self.getTabByNick(nick)[0].enable()
        else:
            self.addNewTab(nick)

        self.connectionManager.newClientAccepted(nick)


    def addNewTab(self, nick=None):
        newTab = QChatTab(self, nick)
        self.chatTabs.addTab(newTab, nick if nick is not None else "New Chat")
        self.chatTabs.setCurrentWidget(newTab)


    def clientReady(self, nick):
        # Use a signal to call the client ready slot on the UI thread since
        # this function is called from a background thread
        self.clientReadySignal.emit(nick)


    @pyqtSlot(str)
    def clientReadySlot(self, nick):
        nick = str(nick)
        tab, tabIndex = self.getTabByNick(nick)
        self.chatTabs.setTabText(tabIndex, nick)
        tab.showNowChattingMessage()

        # Set the window title if the tab is the selected tab
        if tabIndex == self.chatTabs.currentIndex():
            self.setWindowTitle(nick)


    def handleError(self, nick, errorCode):
        self.handleErrorSignal.emit(nick, errorCode)


    @pyqtSlot(str, int)
    def handleErrorSlot(self, nick, errorCode):
        # If no nick was given, disable all tabs
        nick = str(nick)
        if nick == '':
            self.__disableAllTabs()
        else:
            try:
                tab = self.getTabByNick(nick)[0]
                tab.resetOrDisable()
            except:
                self.__disableAllTabs()

        if errorCode == errors.ERR_CONNECTION_ENDED:
            QMessageBox.warning(self, errors.TITLE_CONNECTION_ENDED, errors.CONNECTION_ENDED % (nick))
        elif errorCode == errors.ERR_NICK_NOT_FOUND:
            QMessageBox.information(self, errors.TITLE_NICK_NOT_FOUND, errors.NICK_NOT_FOUND % (nick))
            tab.nick = None
        elif errorCode == errors.ERR_CONNECTION_REJECTED:
            QMessageBox.warning(self, errors.TITLE_CONNECTION_REJECTED, errors.CONNECTION_REJECTED % (nick))
            tab.nick = None
        elif errorCode == errors.ERR_BAD_HANDSHAKE:
            QMessageBox.warning(self, errors.TITLE_PROTOCOL_ERROR, errors.PROTOCOL_ERROR % (nick))
        elif errorCode == errors.ERR_CLIENT_EXISTS:
            QMessageBox.information(self, errors.TITLE_CLIENT_EXISTS, errors.CLIENT_EXISTS % (nick))
        elif errorCode == errors.ERR_SELF_CONNECT:
            QMessageBox.warning(self, errors.TITLE_SELF_CONNECT, errors.SELF_CONNECT)
        elif errorCode == errors.ERR_SERVER_SHUTDOWN:
            QMessageBox.critical(self, errors.TITLE_SERVER_SHUTDOWN, errors.SERVER_SHUTDOWN)
        elif errorCode == errors.ERR_ALREADY_CONNECTED:
            QMessageBox.information(self, errors.TITLE_ALREADY_CONNECTED, errors.ALREADY_CONNECTED % (nick))
        elif errorCode == errors.ERR_INVALID_COMMAND:
            QMessageBox.warning(self, errors.TITLE_INVALID_COMMAND, errors.INVALID_COMMAND % (nick))
        elif errorCode == errors.ERR_NETWORK_ERROR:
            QMessageBox.critical(self, errors.TITLE_NETWORK_ERROR, errors.NETWORK_ERROR)
        elif errorCode == errors.ERR_BAD_HMAC:
            QMessageBox.critical(self, errors.TITLE_BAD_HMAC, errors.BAD_HMAC)
        elif errorCode == errors.ERR_BAD_DECRYPT:
            QMessageBox.warning(self, errors.TITLE_BAD_DECRYPT, errors.BAD_DECRYPT)
        elif errorCode == errors.ERR_KICKED:
            QMessageBox.critical(self, errors.TITLE_KICKED, errors.KICKED)
        elif errorCode == errors.ERR_NICK_IN_USE:
            QMessageBox.warning(self, errors.TITLE_NICK_IN_USE, errors.NICK_IN_USE)
            self.restartCallback()
        elif errorCode == errors.ERR_SMP_CHECK_FAILED:
            QMessageBox.warning(self, errors.TITLE_PROTOCOL_ERROR, errors.PROTOCOL_ERROR % (nick))
            tab.nick = None
        elif errorCode == errors.ERR_SMP_MATCH_FAILED:
            QMessageBox.critical(self, errors.TITLE_SMP_MATCH_FAILED, errors.SMP_MATCH_FAILED)
            tab.nick = None
        elif errorCode == errors.ERR_MESSAGE_REPLAY:
            QMessageBox.critical(self, errors.TITLE_MESSAGE_REPLAY, errors.MESSAGE_REPLAY)
        elif errorCode == errors.ERR_MESSAGE_DELETION:
            QMessageBox.critical(self, errors.TITLE_MESSAGE_DELETION, errors.MESSAGE_DELETION)
        else:
            QMessageBox.warning(self, errors.TITLE_UNKNOWN_ERROR, errors.UNKNOWN_ERROR % (nick))


    def __disableAllTabs(self):
        for i in range(0, self.chatTabs.count()):
            curTab = self.chatTabs.widget(i)
            curTab.resetOrDisable()


    def postMessage(self, command, sourceNick, payload):
        self.sendMessageToTabSignal.emit(command, sourceNick, payload)


    @pyqtSlot(str, str, str)
    def sendMessageToTab(self, command, sourceNick, payload):
        # If a typing command, update the typing status in the tab, otherwise
        # show the message in the tab
        tab, tabIndex = self.getTabByNick(sourceNick)
        if command == constants.COMMAND_TYPING:
            # Show the typing status in the status bar if the tab is the selected tab
            if tabIndex == self.chatTabs.currentIndex():
                payload = int(payload)
                if payload == constants.TYPING_START:
                    self.statusBar.showMessage("%s is typing" % sourceNick)
                elif payload == constants.TYPING_STOP_WITHOUT_TEXT:
                    self.statusBar.showMessage('')
                elif payload == constants.TYPING_STOP_WITH_TEXT:
                    self.statusBar.showMessage("%s has entered text" % sourceNick)
        else:
            tab.appendMessage(payload, constants.RECEIVER)

            # Update the unread message count if the message is not intended for the currently selected tab
            if tabIndex != self.chatTabs.currentIndex():
                tab.unreadCount += 1
                self.chatTabs.setTabText(tabIndex, tab.nick + (" (%d)" % tab.unreadCount))
            else:
                # Clear the typing status if the current tab
                self.statusBar.showMessage('')

            # Show a system notifcation of the new message if not the current window or tab or the
            # scrollbar of the tab isn't at the bottom
            chatLogScrollbar = tab.widgetStack.widget(2).chatLog.verticalScrollBar()
            if not self.isActiveWindow() or tabIndex != self.chatTabs.currentIndex() or \
               chatLogScrollbar.value() != chatLogScrollbar.maximum():
                qtUtils.showDesktopNotification(self.systemTrayIcon, sourceNick, payload)


    @pyqtSlot(int)
    def tabChanged(self, index):
        # Reset the unread count for the tab when it's switched to
        tab = self.chatTabs.widget(index)

        # Change the window title to the nick
        if tab is None or tab.nick is None:
            self.setWindowTitle("Cryptully")
        else:
            self.setWindowTitle(tab.nick)

        if tab is not None and tab.unreadCount != 0:
            tab.unreadCount = 0
            self.chatTabs.setTabText(index, tab.nick)


    @pyqtSlot(int)
    def closeTab(self, index):
        tab = self.chatTabs.widget(index)
        self.connectionManager.closeChat(tab.nick)

        self.chatTabs.removeTab(index)

        # Show a new tab if there are now no tabs left
        if self.chatTabs.count() == 0:
            self.addNewTab()


    def getTabByNick(self, nick):
        for i in range(0, self.chatTabs.count()):
            curTab = self.chatTabs.widget(i)
            if curTab.nick == nick:
                return (curTab, i)
        return None


    def isNickInTabs(self, nick):
        for i in range(0, self.chatTabs.count()):
            curTab = self.chatTabs.widget(i)
            if curTab.nick == nick:
                return True
        return False


    def __setMenubar(self):
        newChatIcon     = QIcon(qtUtils.getAbsoluteImagePath('new_chat.png'))
        helpIcon        = QIcon(qtUtils.getAbsoluteImagePath('help.png'))
        exitIcon        = QIcon(qtUtils.getAbsoluteImagePath('exit.png'))
        menuIcon        = QIcon(qtUtils.getAbsoluteImagePath('menu.png'))

        newChatAction      = QAction(newChatIcon, '&New chat', self)
        helpAction         = QAction(helpIcon, 'Show &help', self)
        exitAction         = QAction(exitIcon, '&Exit', self)

        newChatAction.triggered.connect(lambda: self.addNewTab())
        helpAction.triggered.connect(self.__showHelpDialog)
        exitAction.triggered.connect(self.__exit)

        newChatAction.setShortcut('Ctrl+N')
        helpAction.setShortcut('Ctrl+H')
        exitAction.setShortcut('Ctrl+Q')

        optionsMenu = QMenu()

        optionsMenu.addAction(newChatAction)
        optionsMenu.addAction(helpAction)
        optionsMenu.addAction(exitAction)

        optionsMenuButton = QToolButton()
        newChatButton     = QToolButton()
        exitButton        = QToolButton()

        newChatButton.clicked.connect(lambda: self.addNewTab())
        exitButton.clicked.connect(self.__exit)

        optionsMenuButton.setIcon(menuIcon)
        newChatButton.setIcon(newChatIcon)
        exitButton.setIcon(exitIcon)

        optionsMenuButton.setMenu(optionsMenu)
        optionsMenuButton.setPopupMode(QToolButton.InstantPopup)

        toolbar = QToolBar(self)
        toolbar.addWidget(optionsMenuButton)
        toolbar.addWidget(newChatButton)
        toolbar.addWidget(exitButton)
        self.addToolBar(Qt.LeftToolBarArea, toolbar)


    def __showHelpDialog(self):
        QHelpDialog(self).show()


    def __exit(self):
        if QMessageBox.Yes == QMessageBox.question(self, "Confirm Exit", "Are you sure you want to exit?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No):
            qtUtils.exitApp()
