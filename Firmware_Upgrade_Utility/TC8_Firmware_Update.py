import sys
import binascii
import socket
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow,
    QApplication,
    QWidget,
    QPushButton,
    QVBoxLayout,
    QLineEdit,
    QStackedWidget,
    QFileDialog,
    QLabel,
    QProgressBar,
    QStyle
)
from PySide6.QtGui import QIcon, QFont, QRegularExpressionValidator, QCloseEvent
from PySide6.QtCore import Qt, QRegularExpression, QObject, Slot, Signal, QTimer
from PySide6.QtNetwork import QTcpSocket


class Firmware_Update_App(QMainWindow):
    connected = Signal()
    disconnected = Signal()
    error = Signal(str)
    dataReceived = Signal(bytes)

    def __init__(self):
        super().__init__()

        self.setWindowTitle("TC8 Firmware Updater")
        self.setGeometry(1000,100,800,500);

        #set icon
        icon = QIcon("mts_icon.png")
        self.setWindowIcon(icon) 

        # Create the stacked widget
        self.stacked_widget = QStackedWidget()

        # Create individual pages (widgets)
        self.page1 = QWidget()
        self.page2 = QWidget()

        font_h1 = QFont()
        font_h1.setPointSize(24)
        font_h2 = QFont()
        font_h2.setPointSize(20)
        font_h3 = QFont()
        font_h3.setPointSize(14)
        font_h4 = QFont()
        font_h4.setPointSize(14)
        self.select_button = QPushButton("Select File")
        self.select_button.setFont(font_h2)
        self.select_button.setStyleSheet("""
            QPushButton {
                border: 2px solid #000000;
                border-radius: 5px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #EEEEEE
            }
        """)
        self.drag_label = QLabel("Drag & Drop .bin file")
        self.drag_label.setFont(font_h1)
        self.drag_label.setAlignment(Qt.AlignCenter)

        self.ip_entry = QLineEdit()
        self.ip_entry.setFont(font_h4)
        self.ip_entry.setText("192.168.100.30")
        # Define the regex pattern for a valid IPv4 address
        ip_range = "(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)"
        ip_regex = QRegularExpression(f"^{ip_range}\\.{ip_range}\\.{ip_range}\\.{ip_range}$")

        # Create and set the IP validator
        ip_validator = QRegularExpressionValidator(ip_regex, self.ip_entry)
        self.ip_entry.setValidator(ip_validator)

        self.program_button = QPushButton("Program")
        self.program_button.setFont(font_h2)

        self.program_button.setStyleSheet("""
            QPushButton {
                border: 2px solid #000000;
                border-radius: 5px;
                padding: 5px;
                background-color: #88FF88
            }
            QPushButton:hover {
                background-color: #FFFFFF
            }
        """)
        self.program_button.clicked.connect(self.begin_programming)
        self.status_label = QLabel("Status: Ready to Program")
        self.status_label.setFont(font_h3)
        self.status_label.setAlignment(Qt.AlignLeft)
        self.byte_sum_label = QLabel("Byte Sum: ")
        self.byte_sum_label.setFont(font_h1)
        self.byte_sum_label.setAlignment(Qt.AlignLeft)
        self.crc32_label = QLabel("CRC32 Checksum: ")
        self.crc32_label.setFont(font_h1)
        self.crc32_label.setAlignment(Qt.AlignLeft)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setStyleSheet("""
            QProgressBar {
                border: 2px solid black;
                border-radius: 5px;
                text-align: center;
                background-color: #EEEEEE; /* Background color of the whole bar */
            }
            QProgressBar::chunk {
                background-color: #00FF00; /* Color of the filled portion */
                width: 10px;
                margin: 0px;
            }
        """)
        self.back_button = QPushButton("Back")
        icon = self.back_button.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack)
        self.back_button.setIcon(icon)
        self.back_button.clicked.connect(self.to_page_1)


        self.setup_page1()
        self.setup_page2()

        # Enable drag & drop
        self.setAcceptDrops(True)

        self.file_path = None
        self.socket = None
        self.host = None
        self.port = 502
        self.data = bytearray(b'')
        self.data_length = 0;
        self.step = 0
        self.transactionID = 0
        self.timeElapsed = 0
        self.all_bytes_transmitted = False;
        self.byte_sum_to_length = 0
        self.chip_erased = False

        self.setStyleSheet("background-color: white;")
        
        self.stacked_widget.addWidget(self.page1)
        self.stacked_widget.addWidget(self.page2)

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.stacked_widget)

        # Set the central widget
        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        self.select_button.clicked.connect(self.select_file)


    def set_progress_color(self, color):
        self.progress.setStyleSheet(f"""
            QProgressBar {{
                border: 2px solid black;
                border-radius: 5px;
                text-align: center;
                background-color: #EEEEEE; /* Background color of the whole bar */
            }}
            QProgressBar::chunk {{
                background-color: {color}; /* Color of the filled portion */
                width: 10px;
                margin: 0px;
            }}
        """)


    def to_page_1(self):
        self.program_button.setEnabled(True)
        self.program_button.setStyleSheet("""
            QPushButton {
                border: 2px solid #000000;
                border-radius: 5px;
                padding: 5px;
                background-color: #88FF88
            }
            QPushButton:hover {
                background-color: #FFFFFF
            }
        """)
        self.set_progress_color("#00FF00")
        self.program_button.setEnabled(True)
        self.status_label.setText("Status: Ready to Program")
        self.timer.stop()
        self.disconnect_socket() 
        self.stacked_widget.setCurrentIndex(0)        

    def setup_page1(self):
        layout = QVBoxLayout()
        layout.addWidget(self.drag_label)
        layout.addWidget(self.select_button)
        self.page1.setLayout(layout)
        pass

    def setup_page2(self):
        layout = QVBoxLayout()
        layout.addWidget(self.back_button)
        layout.addWidget(self.byte_sum_label)
        layout.addWidget(self.crc32_label)
        layout.addStretch()
        layout.addWidget(self.ip_entry)
        layout.addWidget(self.program_button)
        layout.addWidget(self.status_label) 
        layout.addWidget(self.progress)
        self.page2.setLayout(layout)
        pass

    # --------------------
    # Drag & Drop Handlers
    # --------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if not urls:
            return

        # Take first file only
        file_path = urls[0].toLocalFile()
        if file_path:
            self.set_file(file_path)

    # --------------------
    # File Selection Logic
    # --------------------
    def select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select File")
        if file_path:
            self.set_file(file_path)

    def set_file(self, file_path):
        self.file_path = file_path
        
        p = Path(self.file_path)
        if p.suffix.lower() == ".bin":
            print("Looks like a BIN file")

            byte_sum = 0
            byte_count = 0

            with open(self.file_path, "rb") as f:
                for byte in f.read():
                    byte_sum += byte
                    byte_count += 1

            self.byte_sum_to_length = byte_sum
            print(hex(self.byte_sum_to_length))

            #fill the rest of the 512kB with 0xFF so we match the Dataman checksum
            while byte_count < 524288:
                byte_sum += 255;
                byte_count += 1

            self.byte_sum_label.setText(f"Byte Sum: 0x{byte_sum:X}")
            #print(hex(byte_sum))

            byte_count = 0

            with open(self.file_path, "rb") as f:    
                for byte in f.read():
                    byte_count += 1

            self.data_length = byte_count
            print(self.data_length)

            with open(self.file_path, "rb") as f:    
                bytes_data = f.read()
                self.data = bytearray(bytes_data)

            while byte_count < 524288:
                self.data.append(255)
                byte_count += 1

            crc = binascii.crc32(self.data) & 0xffffffff
            self.crc32_label.setText(f"CRC-32 Checksum: 0x{crc:X}")
            #print(hex(crc))
            self.progress.setValue(0)
            self.stacked_widget.setCurrentIndex(1)
            #print(bytes(self.data[self.step*256 : self.step*256+256]))
        else:
            print("Invalid file type")

    def begin_programming(self):
        self.program_button.setStyleSheet("background-color: #EEEEEE;")
        self.program_button.setEnabled(False)
        self.status_label.setText("Status: Erasing Flash")

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_timeout)
        self.timer.start(10000)
        
        self.host = self.ip_entry.text()
        self.connect_socket()


    def on_timeout(self):
        self.timer.stop()
        self.status_label.setText("Status: Timeout Ocurred")
        self.set_progress_color("#FF0000")    
        print("Timeout!")

    def connect_socket(self):
        if not self.host or not self.port:
            raise ValueError("Host/port not configured")

        # Clean up old socket if any
        self.disconnect_socket()

        self.socket = QTcpSocket(self)
        self.socket.connected.connect(self._on_connected)
        self.socket.disconnected.connect(self._on_disconnected)
        self.socket.readyRead.connect(self._on_ready_read)
        self.socket.errorOccurred.connect(self._on_error)

        self.socket.connectToHost(self.host, self.port)

    def disconnect_socket(self):
        if self.socket:
            self.socket.disconnectFromHost()
            self.socket.deleteLater()
            self.socket = None

    def send_packet(self, data: bytes):
        if not self.socket or self.socket.state() != QTcpSocket.ConnectedState:
            raise RuntimeError("Not connected")

        self.socket.write(data)

    def start_sequence(self):
        self.all_bytes_transmitted = False;
        self.chip_erased = False;
        self.transactionID = 0
        self.timeElapsed = 0
        packet_data = self.transactionID.to_bytes(2, 'big') + b"\x00\x02" + b"\x00\x00" + b"\x03"
        self.send_packet(packet_data)
        self.step = 0
        bytes_transmitted = self.step * 256
        total_progress = bytes_transmitted / self.data_length
        self.progress.setValue(total_progress)
        self.update_bar()

    def update_bar(self):
        self.timeElapsed += 100
        total_progress = self.timeElapsed / 3500 * 100
        self.progress.setValue(total_progress)        
        if self.timeElapsed >= 3500:
            self.start_data_write()
        else:
            QTimer.singleShot(100, self.update_bar)

    @Slot()
    def _on_connected(self):
        self.connected.emit()
        self.start_sequence()

    @Slot()
    def _on_disconnected(self):
        self.disconnected.emit()

    def start_data_write(self):
        self.chip_erased = True
        self.status_label.setText("Status: Programming")
        self.write_next_page()

    def write_next_page(self):
        self.transactionID += 1
        bytes_transmitted = self.step * 256
        full_packet = 260

        if self.all_bytes_transmitted:
            packet_data = self.transactionID.to_bytes(2, 'big') + b"\x00\x02" + b"\x00\x04" + b"\x02" + self.byte_sum_to_length.to_bytes(4, 'big');
            self.send_packet(packet_data)
            self.all_bytes_transmitted = False; 
        elif bytes_transmitted + 256 < self.data_length:
            packet_data = self.transactionID.to_bytes(2, 'big') + b"\x00\x02" + full_packet.to_bytes(2, 'big') + b"\x01" + bytes_transmitted.to_bytes(4, 'big') + bytes(self.data[self.step*256 : self.step*256+256])
            self.send_packet(packet_data)
            self.step += 1
            total_progress = bytes_transmitted / self.data_length * 100
            self.progress.setValue(total_progress)
        elif bytes_transmitted < self.data_length:
            bytes_left_to_transmit = self.data_length - bytes_transmitted
            partial_packet_size = 4 + bytes_left_to_transmit
            packet_data = self.transactionID.to_bytes(2, 'big') + b"\x00\x02" + partial_packet_size.to_bytes(2, 'big') + b"\x01" + bytes_transmitted.to_bytes(4, 'big') + bytes(self.data[self.step*256 : self.step*256+bytes_left_to_transmit])
            self.send_packet(packet_data)
            self.step += 1
            self.all_bytes_transmitted = True; 
        else:
            self.progress.setValue(100)
            self.program_button.setEnabled(True)
            self.program_button.setStyleSheet("""
                QPushButton {
                    border: 2px solid #000000;
                    border-radius: 5px;
                    padding: 5px;
                    background-color: #88FF88
                }
                QPushButton:hover {
                    background-color: #FFFFFF
                }
            """)
            self.program_button.setEnabled(True)
            self.status_label.setText("Status: Programming Complete")
            self.timer.stop()
            self.disconnect_socket()        

    @Slot()
    def _on_ready_read(self):
        data = bytes(self.socket.readAll())
        self.timer.start(10000)
        received_transaction_ID = (data[0] << 8) | data[1]
        if (received_transaction_ID == self.transactionID) and (data[7] == 1):
            if(self.chip_erased):
                self.write_next_page()
        elif data[7] == 2:
            self.status_label.setText("Status: Byte Sum Failed") 
            self.set_progress_color("#FF0000")    
        elif data[7] == 3:
            self.status_label.setText("Status: File too big") 
            self.set_progress_color("#FF0000")                           
        else:
            self.status_label.setText("Status: An error occured")   
            self.set_progress_color("#FF0000")        
        self.dataReceived.emit(data)


    @Slot()
    def _on_error(self):
        self.error.emit(self.socket.errorString())

    def closeEvent(self, event: QCloseEvent):
        self.disconnect_socket()   
        event.accept()  # or event.ignore()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Firmware_Update_App()
    window.show()
    sys.exit(app.exec())
