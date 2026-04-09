#!/usr/bin/env python3
"""Test to reproduce the highlighting bug"""

import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QTextBrowser, QVBoxLayout, QWidget

app = QApplication(sys.argv)

# Create main window
window = QMainWindow()
central = QWidget()
layout = QVBoxLayout(central)

# Create text browser (chat display)
chat = QTextBrowser()
chat.setStyleSheet("QTextBrowser { background-color: #0F1117; border: none; color: #E2E8F0; font-size: 13px; }")
layout.addWidget(chat)

window.setCentralWidget(central)
window.resize(600, 400)
window.show()

# Add messages BEFORE file
chat.append("<div style='margin:5px;'><b style='color:#63B3ED;'>User1:</b> Message before file</div>")
chat.append("<div style='margin:5px;'><b style='color:#63B3ED;'>User2:</b> Another message before</div>")

# Add file message (with multi-line string like in the code)
file_html = f'''<div style='margin:5px;'>
        <b style='color:#63B3ED;'>User3:</b>
        <div style="background-color:#2D3748; padding:10px; border-radius:5px; margin-top:5px; display:inline-block;">
            <b>📄 File:</b> test.pdf<br>
            <a href="download://test.pdf" style="color:#48BB78; text-decoration:none; font-weight:bold;">⬇️ Click here to Download & Open</a>
        </div></div>'''
chat.append(file_html)

# Add messages AFTER file
chat.append("<div style='margin:5px;'><b style='color:#63B3ED;'>User4:</b> Message after file</div>")
chat.append("<div style='margin:5px;'><b style='color:#63B3ED;'>User5:</b> Another message after</div>")

print("Test window created. Check if messages after file upload look 'highlighted'")
print("Messages before file should look normal, messages after should show the bug")

sys.exit(app.exec())
