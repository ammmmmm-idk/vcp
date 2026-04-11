# VCP - Video Chat Platform

A secure, feature-rich video chat application with end-to-end encryption, real-time messaging, and AI integration.

## Features

- 🔐 **End-to-End Encrypted Chat** - AES-256-GCM encryption for all messages
- 🎥 **Video/Audio Calls** - WebRTC peer-to-peer video conferencing
- 📁 **File Sharing** - Secure file uploads and downloads with TLS
- 🤖 **AI Assistant** - Integrated AI chat powered by Groq
- 🎙️ **Call Transcription** - Real-time transcription using Whisper AI
- 🔑 **OTP Authentication** - Email-based two-factor authentication
- 🏰 **Group Management** - Create and manage chat groups
- 🔒 **Security First** - TLS encryption, input validation, password hashing

---

## Data Flow

### 1. User Signup Flow

```
User Input (Name, Email, Password)
        ↓
[ui_auth.py] - Collects signup data
        ↓
[validators.py] - Validates email format, password strength, username
        ↓
[client.py] - Sends signup request over TLS
        ↓
[server.py] - Receives request
        ↓
[protocol_validator.py] - Validates message schema
        ↓
[auth_service.py] - Generates 6-digit OTP, sets 5-minute expiration
        ↓
[email_service.py] - Sends OTP via SMTP
        ↓
[User] - Receives OTP email
        ↓
[ui_auth.py] - User enters OTP code
        ↓
[server.py] - Validates OTP
        ↓
[auth_service.py] - Hashes password with Argon2
        ↓
[database.py] - Creates user account, stores hashed password
        ↓
[server.py] - Generates session token
        ↓
[database.py] - Hashes and stores session token (SHA-256)
        ↓
[client.py] - Receives session token (plaintext)
        ↓
[Gui.py] - User logged in, shows portal
```

### 2. User Login Flow

```
User Input (Email, Password)
        ↓
[ui_auth.py] - Collects login credentials
        ↓
[validators.py] - Validates email format
        ↓
[client.py] - Sends login request over TLS
        ↓
[server.py] - Receives request
        ↓
[database.py] - Retrieves user by email
        ↓
[auth_service.py] - Verifies password with Argon2
        ↓
[auth_service.py] - Generates OTP
        ↓
[email_service.py] - Sends OTP via email
        ↓
[User] - Enters OTP
        ↓
[server.py] - Validates OTP
        ↓
[server.py] - Creates session token
        ↓
[database.py] - Stores hashed token
        ↓
[client.py] - Stores session token
        ↓
[database.py] - Retrieves user's groups
        ↓
[Gui.py] - Shows portal with user's groups
```

### 3. Creating a Group Flow

```
User clicks "Create Group"
        ↓
[ui_portal.py] - Shows create group dialog
        ↓
User enters group name
        ↓
[validators.py] - Validates group name (length, characters)
        ↓
[client.py] - Sends create_group request over TLS
        ↓
[server.py] - Receives request
        ↓
[message_encryption.py] - Generates unique AES-256 key for group
        ↓
[db_encryption.py] - Encrypts the group encryption key
        ↓
[database.py] - Creates group with encrypted key, sets user as owner
        ↓
[database.py] - Adds user to group members
        ↓
[server.py] - Sends group_created response with encryption key
        ↓
[client.py] - Stores encryption key for this group
        ↓
[Gui.py] - Updates group list, shows new group
```

### 4. Joining a Group Flow

```
User selects group from list
        ↓
[ui_portal.py] - User clicks on group
        ↓
[client.py] - Sends join request with group_id
        ↓
[server.py] - Validates user has access to group
        ↓
[database.py] - Retrieves group encryption key (encrypted)
        ↓
[db_encryption.py] - Decrypts the encryption key
        ↓
[database.py] - Retrieves last 50 messages (encrypted)
        ↓
[db_encryption.py] - Decrypts each message
        ↓
[server.py] - Sends history with encryption key
        ↓
[client.py] - Stores encryption key for this group
        ↓
[message_encryption.py] - Initializes cipher with group key
        ↓
[Gui.py] - Displays chat history
        ↓
[server.py] - Broadcasts user list to all members
        ↓
[Gui.py] - Updates online users list
```

### 5. Sending a Chat Message Flow

```
User types message and presses Send
        ↓
[Gui.py] - Captures message text
        ↓
[validators.py] - Validates message (length, special characters)
        ↓
[client.py] - Gets encryption key for current group
        ↓
[message_encryption.py] - Encrypts message with AES-256-GCM
        ↓
                    Generates random 12-byte nonce
                    Encrypts message → ciphertext
                    Returns {nonce, ciphertext} as base64
        ↓
[client.py] - Sends encrypted message over TLS
        ↓
[server.py] - Receives encrypted message
        ↓
[protocol_validator.py] - Validates message schema
        ↓
[database.py] - Gets group encryption key (encrypted)
        ↓
[db_encryption.py] - Decrypts the encryption key
        ↓
[message_encryption.py] - Decrypts message to validate/store
        ↓
[validators.py] - Validates decrypted message content
        ↓
[server.py] - Checks rate limiting (8 messages per 10 seconds)
        ↓
[db_encryption.py] - Encrypts message for database storage
        ↓
[database.py] - Saves encrypted message to database
        ↓
[server.py] - Broadcasts encrypted message to all group members
        ↓
[client.py] - Receives encrypted message
        ↓
[message_encryption.py] - Decrypts message with group key
        ↓
[Gui.py] - Displays message in chat
```

### 6. File Upload Flow

```
User clicks "Attach File"
        ↓
[Gui.py] - Shows file picker dialog
        ↓
User selects file
        ↓
[attachment_security.py] - Validates filename and extension
        ↓
[file_client.py] - Opens TLS connection to file server (port 8889)
        ↓
[protocol.py] - Sends file header (action='U', filename, filesize)
        ↓
[file_client.py] - Streams file in 8KB chunks
        ↓
[file_server.py] - Receives file over TLS
        ↓
[attachment_security.py] - Validates filename (prevent path traversal)
        ↓
[file_server.py] - Saves to vcp_uploads/ directory
        ↓
[file_server.py] - Sends success response
        ↓
[client.py] - Sends file notification to chat server
        ↓
[server.py] - Broadcasts file notification to group
        ↓
[Gui.py] - Displays file as download button/image preview
```

### 7. File Download Flow

```
User clicks on file/download button
        ↓
[Gui.py] - Shows save location dialog (or uses cache)
        ↓
[file_client.py] - Checks VCP_Cache/ for cached copy
        ↓
If not cached:
        ↓
[file_client.py] - Opens TLS connection to file server (port 8889)
        ↓
[protocol.py] - Sends download request (action='D', filename)
        ↓
[file_server.py] - Reads file from vcp_uploads/
        ↓
[file_server.py] - Sends file header + file data in 8KB chunks
        ↓
[file_client.py] - Receives and saves file
        ↓
[Gui.py] - Opens/displays file
```

### 8. Video Call Flow

```
User clicks "Start Call"
        ↓
[ui_video.py] - Opens video call window
        ↓
[webrtc_thread.py] - Starts WebRTC thread
        ↓
[media_engine.py] - Initializes camera and microphone
        ↓
[signaling.py] - Connects to signaling server (port 8890) over TLS
        ↓
[video_server.py] - Manages peer connections for the group
        ↓
[rtc_peer.py] - Creates RTCPeerConnection
        ↓
[webrtc_thread.py] - Generates SDP offer
        ↓
[signaling.py] - Sends offer to signaling server
        ↓
[video_server.py] - Forwards offer to other peers
        ↓
[Other User's rtc_peer.py] - Receives offer, generates answer
        ↓
[signaling.py] - Exchanges ICE candidates
        ↓
[WebRTC P2P Connection Established]
        ↓
[media_engine.py] - Streams video/audio directly peer-to-peer
        ↓
[ui_video.py] - Displays local and remote video
        ↓
[media_engine.py] - Monitors audio levels
        ↓
If audio level > 100:
        ↓
[media_engine.py] - Buffers audio for transcription
        ↓
[transcription_service.py] - Sends to Groq Whisper API
        ↓
[ui_video.py] - Displays transcription
        ↓
[call_ai_state.py] - Stores transcription for AI summary
```

### 9. AI Assistant Chat Flow

```
User types message to AI and presses Send
        ↓
[Gui.py] - Captures message
        ↓
[validators.py] - Sanitizes AI prompt (injection prevention)
        ↓
[client.py] - Sends assistant_chat request
        ↓
[server.py] - Receives AI chat request
        ↓
[database.py] - Retrieves recent AI conversation history (24 messages)
        ↓
[server.py] - Forwards to AI service
        ↓
[ai_service.py] - Sends to Groq API with conversation context
        ↓
[Groq API] - Generates AI response
        ↓
[ai_service.py] - Receives response
        ↓
[database.py] - Saves user message and AI response
        ↓
[server.py] - Broadcasts AI response to group
        ↓
[Gui.py] - Displays AI response in chat (purple color)
```

### 10. Security Data Flow (TLS + Encryption)

```
CLIENT SIDE:
User Message: "Hello World"
        ↓
[message_encryption.py] - Encrypts with group key
        → Encrypted: "x7dH3k9..." (base64)
        ↓
[client.py] - Wraps in JSON protocol
        ↓
[ssl.py] - TLS encryption (additional layer)
        → Double encrypted over network
        ↓

NETWORK: TLS-encrypted TCP stream

        ↓
SERVER SIDE:
[ssl.py] - TLS decryption (first layer)
        ↓
[server.py] - Receives encrypted message payload
        ↓
[message_encryption.py] - Decrypts with group key
        → Plaintext: "Hello World"
        ↓
[validators.py] - Validates content
        ↓
[db_encryption.py] - Re-encrypts for storage with master key
        ↓
[database.py] - Stores: "k3Hd7x..." (different encryption)
        ↓
[server.py] - Broadcasts encrypted message to peers
        ↓

NETWORK: TLS-encrypted TCP stream

        ↓
OTHER CLIENTS:
[ssl.py] - TLS decryption
        ↓
[client.py] - Receives encrypted payload
        ↓
[message_encryption.py] - Decrypts with group key
        → Plaintext: "Hello World"
        ↓
[Gui.py] - Displays message
```

---

## Third-Party Libraries

### **Core Framework & GUI**

#### **PyQt6** - GUI Framework
- **Purpose:** Desktop application GUI framework
- **Why:** Cross-platform (Windows, macOS, Linux), mature ecosystem, excellent documentation
- **Alternatives Considered:**
  - *Tkinter:* Too basic, limited styling capabilities
  - *wxPython:* Less modern, smaller community
  - *Kivy:* Mobile-focused, overkill for desktop
- **Verdict:** PyQt6 offers best balance of features, performance, and developer experience

#### **qasync** - Asyncio integration for PyQt
- **Purpose:** Bridge between PyQt event loop and Python asyncio
- **Why:** Enables async/await network operations without blocking GUI
- **Alternatives Considered:**
  - *QThreads:* More complex, harder to maintain
  - *Blocking sync calls:* Would freeze UI
- **Verdict:** qasync provides seamless async integration with PyQt

---

### **Networking & Communication**

#### **aiosqlite** - Async SQLite
- **Purpose:** Asynchronous database operations
- **Why:** Non-blocking database queries, works with asyncio event loop
- **Alternatives Considered:**
  - *sqlite3 (built-in):* Blocking, would freeze network operations
  - *PostgreSQL/MySQL:* Overkill for school project, requires separate server
- **Verdict:** aiosqlite perfect for local async database needs

#### **aiortc** - WebRTC Implementation
- **Purpose:** Peer-to-peer video/audio calling
- **Why:** Pure Python WebRTC implementation, no browser required
- **Alternatives Considered:**
  - *Browser WebRTC + Flask:* Requires browser, more complex architecture
  - *Jitsi/Zoom SDK:* Paid, cloud-dependent
  - *GStreamer:* Lower-level, steeper learning curve
- **Verdict:** aiortc offers complete WebRTC in Python without external dependencies

#### **aiohttp** - Async HTTP Client
- **Purpose:** API calls (Groq AI, Tavily Search)
- **Why:** Async HTTP requests, integrates with asyncio
- **Alternatives Considered:**
  - *requests:* Blocking, would require thread pool
  - *httpx:* Similar, but aiohttp more mature for asyncio
- **Verdict:** Standard choice for async HTTP in Python

---

### **Security & Encryption**

#### **cryptography** - Encryption Library
- **Purpose:** AES-256-GCM encryption for messages and database
- **Why:** Industry-standard, secure, well-audited
- **Alternatives Considered:**
  - *PyCrypto:* Abandoned, security vulnerabilities
  - *hashlib (built-in):* No AES-GCM support
  - *Manual OpenSSL bindings:* Too low-level, error-prone
- **Verdict:** cryptography is the gold standard for Python encryption

#### **argon2-cffi** - Password Hashing
- **Purpose:** Secure password hashing
- **Why:** Argon2 won Password Hashing Competition, resistant to GPU attacks
- **Alternatives Considered:**
  - *bcrypt:* Good but slower than Argon2
  - *scrypt:* Less resistance to side-channel attacks
  - *SHA-256:* Not designed for passwords, too fast
- **Verdict:** Argon2 is the most secure modern password hashing algorithm

---

### **Media Processing**

#### **opencv-python (cv2)** - Video Processing
- **Purpose:** Camera capture and video frame processing
- **Why:** Industry standard, extensive functionality, hardware acceleration
- **Alternatives Considered:**
  - *Pillow:* Images only, no video capture
  - *PyAV:* Lower-level, more complex
- **Verdict:** OpenCV is the de facto standard for computer vision

#### **sounddevice** - Audio I/O
- **Purpose:** Microphone and speaker access
- **Why:** Cross-platform, low latency, simple API
- **Alternatives Considered:**
  - *PyAudio:* Unmaintained, installation issues
  - *python-sounddevice:* Same library, sounddevice is the canonical name
- **Verdict:** Most reliable cross-platform audio library

#### **numpy** - Numerical Operations
- **Purpose:** Audio/video data manipulation, array operations
- **Why:** Fast C-optimized operations, required by cv2 and sounddevice
- **Alternatives Considered:**
  - *Pure Python lists:* Too slow for real-time A/V processing
- **Verdict:** Essential for any media processing in Python

#### **av (PyAV)** - Audio/Video Codecs
- **Purpose:** Audio encoding/decoding for WebRTC
- **Why:** Python bindings for FFmpeg, required by aiortc
- **Alternatives Considered:**
  - *Direct FFmpeg:* Subprocess overhead
  - *moviepy:* Too high-level, not for streaming
- **Verdict:** Required dependency for aiortc WebRTC

---

### **AI & Machine Learning**

#### **groq** - Groq API Client
- **Purpose:** AI chat and audio transcription (Whisper)
- **Why:** Fastest LLM inference, free tier, excellent API
- **Alternatives Considered:**
  - *OpenAI API:* More expensive, slower
  - *Local LLaMA:* Requires powerful GPU, complex setup
  - *Anthropic Claude:* More expensive
- **Verdict:** Groq offers best performance-to-cost ratio for school project

#### **requests** - HTTP Library (for Tavily)
- **Purpose:** Web search API calls
- **Why:** Simple, synchronous, used in non-critical path
- **Alternatives Considered:**
  - *aiohttp:* Overkill for infrequent search calls
- **Verdict:** Standard library for simple HTTP requests

---

### **Email & Environment**

#### **python-dotenv** - Environment Variables
- **Purpose:** Load API keys and credentials from .env file
- **Why:** Secure credential management, keeps secrets out of code
- **Alternatives Considered:**
  - *Hard-coded:* Insecure, exposes credentials in git
  - *config.json:* Less standard, no auto-loading
- **Verdict:** Industry standard for environment variable management

#### **aiosmtplib** - Async SMTP
- **Purpose:** Send OTP emails asynchronously
- **Why:** Non-blocking email sending
- **Alternatives Considered:**
  - *smtplib (built-in):* Blocking, would freeze server
  - *Third-party email service:* Adds dependency, costs money
- **Verdict:** Simple async email sending without external services

---

### **Why NOT Use Other Common Alternatives?**

#### **Django/Flask** - NOT USED
- **Reason:** Desktop app, not web app. PyQt provides better UX for this use case.

#### **Socket.io** - NOT USED
- **Reason:** Raw TCP with custom protocol gives more control and better performance.

#### **Redis/Memcached** - NOT USED
- **Reason:** SQLite sufficient for school project scale, no need for external cache.

#### **Docker** - NOT USED
- **Reason:** Desktop application for local/LAN use, containerization not needed.

#### **Electron** - NOT USED
- **Reason:** Python ecosystem preferred, PyQt more native than web stack.

#### **Twilio/SendGrid** - NOT USED
- **Reason:** Direct SMTP cheaper and simpler for school project, no vendor lock-in.

---

## Project Statistics

- **Lines of Code:** ~8,000+
- **Files:** 31 Python modules
- **Security Features:** 8 implemented (TLS, E2E encryption, input validation, etc.)
- **Third-Party Libraries:** 15 (excluding transitive dependencies)
- **Supported Platforms:** Windows, macOS, Linux

---

## Architecture Decisions

### **Why TCP Instead of WebSockets?**
- **Control:** Custom protocol gives fine-grained control over message framing
- **Simplicity:** No HTTP overhead for persistent connections
- **TLS Integration:** Easier to add TLS layer to raw TCP

### **Why Separate Servers for Chat/Files/Video?**
- **Scalability:** Can run on different ports/machines
- **Security:** File server isolated from chat logic
- **Concurrency:** File transfers don't block chat messages

### **Why SQLite Instead of PostgreSQL?**
- **Simplicity:** No separate database server to manage
- **Portability:** Single file database, easy to backup
- **Sufficient:** Handles dozens of users easily for school project

### **Why Asyncio Instead of Threading?**
- **Efficiency:** Single-threaded async handles thousands of connections
- **Simplicity:** No race conditions, locks, or synchronization issues
- **Modern:** Asyncio is Python's recommended approach for I/O-bound tasks

### **Why End-to-End Encryption for Group Chat?**
- **Learning:** Demonstrates understanding of cryptography concepts
- **Security:** Even server admin can't read messages
- **Industry Practice:** Signal, WhatsApp use similar E2E encryption

---

## License

This is a school project for educational purposes.

---

## Authors

**Ron Sherman** - VCP Development Team

## Acknowledgments

- PyQt6 for the excellent GUI framework
- Groq for fast and affordable AI API
- aiortc for making WebRTC accessible in Python
