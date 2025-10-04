# Script para atualizar repositório Git automaticamente
# Uso: .\gitupdate.ps1

Write-Host "🔄 Iniciando atualização do repositório..." -ForegroundColor Cyan

# 1. Buscar todas as atualizações do repositório remoto
Write-Host "📡 Buscando atualizações remotas..." -ForegroundColor Yellow
git fetch origin

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Erro ao buscar atualizações remotas!" -ForegroundColor Red
    exit 1
}

# 2. Verificar branches remotas disponíveis
Write-Host "🌿 Verificando branches disponíveis..." -ForegroundColor Yellow
git branch -r

# 3. Verificar branch atual
$currentBranch = git branch --show-current
Write-Host "📍 Branch atual: $currentBranch" -ForegroundColor Green

# 4. Verificar se há atualizações pendentes
Write-Host "🔍 Verificando status..." -ForegroundColor Yellow
git status --porcelain

$status = git status --porcelain
if ($status) {
    Write-Host "⚠️  Você tem alterações não commitadas!" -ForegroundColor Red
    Write-Host "   Por favor, faça commit ou stash antes de atualizar." -ForegroundColor Red
    exit 1
}

# 5. Verificar se a branch local está atrasada
$behind = git rev-list HEAD..origin/$currentBranch --count 2>$null
if ($behind -and $behind -gt 0) {
    Write-Host "⬇️  Sua branch está $behind commits atrasada. Atualizando..." -ForegroundColor Yellow
    git pull origin $currentBranch
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Branch atualizada com sucesso!" -ForegroundColor Green
    } else {
        Write-Host "❌ Erro ao atualizar a branch!" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "✅ Sua branch já está atualizada!" -ForegroundColor Green
}

# 6. Mostrar log dos últimos commits
Write-Host "📜 Últimos 5 commits:" -ForegroundColor Yellow
git log --oneline -5

Write-Host "🎉 Atualização concluída! Você pode começar a codificar." -ForegroundColor Green