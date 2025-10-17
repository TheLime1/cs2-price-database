# Clear ChromeDriver Cache Script
# This removes the corrupted 32-bit ChromeDriver that was downloaded

Write-Host "🧹 Clearing ChromeDriver cache..." -ForegroundColor Yellow

$cachePath = "$env:USERPROFILE\.wdm"

if (Test-Path $cachePath) {
    Write-Host "📂 Found cache at: $cachePath" -ForegroundColor Cyan
    
    try {
        Remove-Item -Path $cachePath -Recurse -Force -ErrorAction Stop
        Write-Host "✅ ChromeDriver cache cleared successfully!" -ForegroundColor Green
        Write-Host "💡 Next run will download the correct 64-bit version" -ForegroundColor Yellow
    }
    catch {
        Write-Host "❌ Error clearing cache: $_" -ForegroundColor Red
        Write-Host "💡 Try manually deleting: $cachePath" -ForegroundColor Yellow
    }
}
else {
    Write-Host "ℹ️  No ChromeDriver cache found at: $cachePath" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "🚀 Now you can run: python collect_prices.py --limit 1" -ForegroundColor Green
