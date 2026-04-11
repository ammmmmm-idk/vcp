"""
VCP UI Styles
=============
Centralized stylesheet definitions for consistent UI theming.

Theme: Dark mode
Colors:
- Background: Dark grays (#0F1117, #1A202C)
- Accent: Blues (#3B82F6, #63B3ED)
- Text: Light gray (#E2E8F0)
- Borders: Subtle grays

Styles: Buttons, inputs, text areas, scrollbars, containers
"""
# Save as: styles.py

class VCPStyles:
    """Unified QSS for the VCP Application."""

    AUTH_STYLE = """
        QMainWindow { background-color: #0F1117; }
        QFrame#AuthCard {
            background-color: #1A1D27;
            border: 1px solid #2D3748;
            border-radius: 12px;
            min-width: 350px;
        }
        QLabel#Title { font-size: 32px; font-weight: bold; color: #63B3ED; margin-bottom: 5px; }
        QLabel#Subtitle { font-size: 14px; color: #A0AEC0; margin-bottom: 20px; }
        QLineEdit {
            background-color: #0F1117; border: 1px solid #4A5568;
            padding: 12px; border-radius: 6px; color: #E2E8F0;
            margin-bottom: 10px;
        }
        QPushButton#PrimaryBtn {
            background-color: #3182CE; color: white; padding: 12px;
            border-radius: 6px; font-weight: bold; margin-top: 10px;
        }
        QPushButton#LinkBtn {
            background-color: transparent; color: #63B3ED; border: none; 
            text-decoration: underline; font-size: 13px; margin-top: 5px;
        }
    """

    PORTAL_STYLE = """
        QFrame#GroupSwitcher {
            background-color: #090B10;
            border-right: 1px solid #2D3748;
            min-width: 70px;
            max-width: 70px;
        }
        QPushButton#GroupIcon {
            background-color: #2D3748; color: white; border-radius: 25px;
            font-weight: bold; font-size: 14px; margin: 10px 5px;
        }
        QPushButton#GroupIcon:hover { background-color: #4A5568; }
        QPushButton#GroupIcon[active="true"] { border: 2px solid #63B3ED; background-color: #2B6CB0; }

        QPushButton#AiIcon {
            background-color: #6B46C1; color: white; border-radius: 25px;
            font-weight: bold; font-size: 14px; margin: 10px 5px;
        }
        QPushButton#AiIcon:hover { background-color: #805AD5; }
        QPushButton#AiIcon[active="true"] { border: 2px solid #D6BCFA; background-color: #553C9A; }

        QPushButton#AddGroupBtn {
            background-color: #2F855A; color: white; border-radius: 25px;
            font-weight: bold; font-size: 20px; margin: 10px 5px;
        }
        QPushButton#AddGroupBtn:hover { background-color: #38A169; }

        QFrame#Sidebar { background-color: #1A1D27; border-left: 1px solid #2D3748; }
        QFrame#VideoTile { background-color: #000000; border: 2px solid #2D3748; border-radius: 10px; }
        QFrame#ActionBar { background-color: #1A1D27; border-top: 1px solid #2D3748; }

        QPushButton#InviteBtn { background-color: #2F855A; color: white; font-weight: bold; padding: 8px 15px; border-radius: 6px; }
        QPushButton#ControlBtn { background-color: #2D3748; color: white; border-radius: 20px; min-width: 100px; min-height: 40px; font-size: 12px; }

        QTextBrowser#ChatDisplay { background-color: #0F1117; border: none; color: #E2E8F0; font-size: 13px; }
        QPushButton#AttachBtn { background-color: #2D3748; color: white; border-radius: 6px; font-weight: bold; font-size: 16px; }
        QPushButton#AttachBtn:hover { background-color: #4A5568; }
        QPushButton#SendBtn { background-color: #3182CE; color: white; border-radius: 6px; font-weight: bold; }
    """

    MODAL_STYLE = """
        QDialog { background-color: #1A1D27; border: 1px solid #4A5568; border-radius: 12px; }
        QPushButton#FilterCard { background-color: #2D3748; color: #E2E8F0; border-radius: 8px; padding: 15px; font-weight: 500; }
        QPushButton#FilterCard:hover { border: 2px solid #63B3ED; }
        QPushButton#DangerBtn { background-color: #E53E3E; color: white; font-weight: bold; border-radius: 6px; padding: 10px; }
    """