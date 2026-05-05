@echo off
:: Enhanced script for generating Root CA and Server certificates using OpenSSL

:: Check for rootCA.conf file
if not exist rootCA.conf (
    echo [Error: rootCA.conf not found. Exiting...]
    exit /b 1
)

:: Generate Root CA if it doesn't exist
if not exist rootCA.crt (
    echo [Generating Root CA private key and Certificate...]
    openssl req -x509 -sha256 -days 3650 -nodes -newkey rsa:2048 -keyout rootCA.key -out rootCA.crt -config rootCA.conf
    if errorlevel 1 (
        echo [Error during Root CA generation. Exiting...]
        exit /b 1
    )
) else (
    echo [Root CA certificate exists, skipping generation...])

:: Generate Server Private Key if it doesn't exist
if not exist server.key (
    echo [Generating Server private key file: server.key...]
    openssl genrsa -out server.key 2048
    if errorlevel 1 (
        echo [Error generating server key. Exiting...]
        exit /b 1
    )
) else (
    echo [Server private key file exists, skipping generation...])

:: Generate Server CSR
echo [Generating CSR file with Server Private Key...]
openssl req -new -key server.key -out server.csr -config serverCSR.conf
if errorlevel 1 (
    echo [Error generating CSR. Exiting...]
    exit /b 1
)

:: Remove old serial file if it exists
if exist rootCA.srl del rootCA.srl

:: Check for server.conf file
if not exist server.conf (
    echo [Error: server.conf not found. Exiting...]
    exit /b 1
)

:: Sign Server Certificate with Root CA
echo [Signing server certificate with Root CA and generating server.crt file...]
openssl x509 -req -in server.csr -CA rootCA.crt -CAkey rootCA.key -CAcreateserial -out server.crt -days 3650 -sha256 -extfile server.conf -extensions v3_server
if errorlevel 1 (
    echo [Error signing server certificate. Exiting...]
    exit /b 1
)

echo [Certificate generation complete!]
pause
