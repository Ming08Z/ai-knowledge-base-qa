#Requires -RunAsAdministrator

$ErrorActionPreference = "Stop"
$serviceName = "MySQL80"
$mysqlServer = "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqld.exe"
$mysqlClient = "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe"
$defaultsFile = "C:\ProgramData\MySQL\MySQL Server 8.0\my.ini"
$projectRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $projectRoot ".env"
$manualServer = $null
$plainPassword = $null

function ConvertTo-PlainText([Security.SecureString]$SecureValue) {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

function Invoke-LocalMySql([string]$Sql, [string]$Password = "") {
    $startInfo = New-Object Diagnostics.ProcessStartInfo
    $startInfo.FileName = $mysqlClient
    $startInfo.Arguments = "--protocol=MEMORY --user=root --batch --skip-column-names"
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    if ($Password) {
        $startInfo.EnvironmentVariables["MYSQL_PWD"] = $Password
    }
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $startInfo
    [void]$process.Start()
    $process.StandardInput.WriteLine($Sql)
    $process.StandardInput.Close()
    $output = $process.StandardOutput.ReadToEnd()
    $errorText = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) {
        throw ($errorText.Trim() + " " + $output.Trim()).Trim()
    }
    return $output.Trim()
}

try {
    Write-Host "MySQL root password reset" -ForegroundColor Cyan
    Write-Host "Use at least 12 printable characters. Single quote and backslash are not allowed."
    $first = Read-Host "New root password" -AsSecureString
    $second = Read-Host "Confirm new root password" -AsSecureString
    $plainPassword = ConvertTo-PlainText $first
    $confirmation = ConvertTo-PlainText $second
    if ($plainPassword -cne $confirmation) {
        throw "The two passwords do not match."
    }
    if ($plainPassword.Length -lt 12 -or $plainPassword -notmatch '^[\x20-\x7E]+$' -or $plainPassword.Contains("'") -or $plainPassword.Contains("\")) {
        throw "Password must contain at least 12 printable characters and cannot contain single quote or backslash."
    }

    Write-Host "Stopping MySQL80..."
    Stop-Service -Name $serviceName -Force
    $serverArguments = "--defaults-file=`"$defaultsFile`" --console --skip-grant-tables --skip-networking --shared-memory"
    $manualServer = Start-Process -FilePath $mysqlServer -ArgumentList $serverArguments -WindowStyle Hidden -PassThru

    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 500
        if ($manualServer.HasExited) {
            throw "Temporary MySQL server exited before password reset."
        }
        try {
            [void](Invoke-LocalMySql "SELECT 1;")
            $ready = $true
            break
        }
        catch {}
    }
    if (-not $ready) {
        throw "Temporary MySQL server did not become ready."
    }

    $randomBytes = New-Object byte[] 24
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    $generator.GetBytes($randomBytes)
    $generator.Dispose()
    $appPassword = [Convert]::ToBase64String($randomBytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
    $database = "ai_knowledge_base"
    $appUser = "ai_kb_user"
    $sql = @"
FLUSH PRIVILEGES;
ALTER USER 'root'@'localhost' IDENTIFIED WITH caching_sha2_password BY '$plainPassword';
CREATE DATABASE IF NOT EXISTS ``$database`` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER IF NOT EXISTS '$appUser'@'localhost' IDENTIFIED BY '$appPassword';
ALTER USER '$appUser'@'localhost' IDENTIFIED BY '$appPassword';
GRANT ALL PRIVILEGES ON ``$database``.* TO '$appUser'@'localhost';
CREATE USER IF NOT EXISTS '$appUser'@'127.0.0.1' IDENTIFIED BY '$appPassword';
ALTER USER '$appUser'@'127.0.0.1' IDENTIFIED BY '$appPassword';
GRANT ALL PRIVILEGES ON ``$database``.* TO '$appUser'@'127.0.0.1';
FLUSH PRIVILEGES;
"@
    [void](Invoke-LocalMySql $sql)

    $encodedPassword = [Uri]::EscapeDataString($appPassword)
    $databaseUrl = "DATABASE_URL=mysql+pymysql://${appUser}:${encodedPassword}@127.0.0.1:3306/${database}?charset=utf8mb4"
    $existingLines = @()
    if (Test-Path -LiteralPath $envFile) {
        $existingLines = @(Get-Content -LiteralPath $envFile | Where-Object { -not $_.StartsWith("DATABASE_URL=") })
    }
    [IO.File]::WriteAllLines($envFile, @($existingLines + $databaseUrl), (New-Object Text.UTF8Encoding($false)))
}
finally {
    $plainPassword = $null
    if ($manualServer -and -not $manualServer.HasExited) {
        $manualServer.Kill()
        $manualServer.WaitForExit()
    }
    $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if ($service -and $service.Status -ne "Running") {
        Start-Service -Name $serviceName
    }
}

Write-Host "Root password reset and project database initialized successfully." -ForegroundColor Green
Write-Host "Keep this root password in a password manager. The application uses its own generated account."
Start-Process -FilePath (Join-Path $projectRoot "start.bat") -WorkingDirectory $projectRoot
Read-Host "Press Enter to close this administrator window"
