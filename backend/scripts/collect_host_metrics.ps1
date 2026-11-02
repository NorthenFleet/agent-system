# Read-only Windows probe: no installation, service/configuration changes or jobs.
$ErrorActionPreference = 'Stop'
$os = Get-CimInstance Win32_OperatingSystem
$computer = Get-CimInstance Win32_ComputerSystem
$cpu = @(Get-CimInstance Win32_Processor)
$disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$($env:SystemDrive)'"
$total = [long]$os.TotalVisibleMemorySize * 1024
$available = [long]$os.FreePhysicalMemory * 1024
$gpus = @()
$gpuState = 'unavailable'
try {
  $gpus = @(Get-CimInstance Win32_VideoController | ForEach-Object {
    @{ name = $_.Name; memory_total_bytes = $null; memory_used_bytes = $null; utilization_percent = $null }
  })
  $gpuState = 'inventory_only'
} catch {}
@{
  hostname = $env:COMPUTERNAME; os_version = $os.Caption; architecture = $os.OSArchitecture
  hardware_model = $computer.Model; cpu_logical_count = $computer.NumberOfLogicalProcessors
  cpu_percent = ($cpu | Measure-Object LoadPercentage -Average).Average
  memory_total_bytes = $total; memory_available_bytes = $available
  memory_percent = [math]::Round((1 - $available / $total) * 100, 1)
  disk_total_bytes = $disk.Size; disk_free_bytes = $disk.FreeSpace
  gpus = $gpus; gpu_probe_state = $gpuState; docker_state = 'unknown'; docker_version = $null
} | ConvertTo-Json -Depth 5 -Compress
