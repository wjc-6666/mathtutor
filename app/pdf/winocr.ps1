$ErrorActionPreference='Stop'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null=[Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
$null=[Windows.Storage.FileAccessMode,Windows.Storage,ContentType=WindowsRuntime]
$null=[Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
$null=[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
$null=[Windows.Media.Ocr.OcrResult,Windows.Foundation,ContentType=WindowsRuntime]
$null=[Windows.Globalization.Language,Windows.Globalization,ContentType=WindowsRuntime]
$taskAwait=[System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {$_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'} | Select-Object -First 1
function Await-WinRT($operation,$type){
    $task=$taskAwait.MakeGenericMethod($type).Invoke($null,@($operation))
    $task.GetAwaiter().GetResult()
}
$taskEngine=[Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage((New-Object Windows.Globalization.Language 'zh-Hans-CN'))
if($null -eq $taskEngine){throw 'Windows 简体中文 OCR 语言包未安装'}
while($null -ne ($taskLine=[Console]::ReadLine())){
    try{
        $taskRequest=$taskLine | ConvertFrom-Json
        $taskFile=Await-WinRT ([Windows.Storage.StorageFile]::GetFileFromPathAsync($taskRequest.path)) ([Windows.Storage.StorageFile])
        $taskStream=Await-WinRT ($taskFile.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
        try{
            $taskDecoder=Await-WinRT ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($taskStream)) ([Windows.Graphics.Imaging.BitmapDecoder])
            $taskBitmap=Await-WinRT ($taskDecoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
            try{
                $taskResult=Await-WinRT ($taskEngine.RecognizeAsync($taskBitmap)) ([Windows.Media.Ocr.OcrResult])
                $taskLines=@($taskResult.Lines | ForEach-Object {$_.Text})
                [Console]::WriteLine((@{ok=$true;text=($taskLines -join "`n");lines=$taskLines;engine='windows-zh-Hans-CN';version=[Environment]::OSVersion.Version.ToString()} | ConvertTo-Json -Compress -Depth 5))
            }finally{$taskBitmap.Dispose()}
        }finally{$taskStream.Dispose()}
    }catch{
        [Console]::WriteLine((@{ok=$false;error=$_.Exception.Message} | ConvertTo-Json -Compress))
    }
}
