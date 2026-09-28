#!/usr/bin/env bash
# Bien dich PlayerMessage.vi.resx thanh satellite assembly cho OpenMU.
# Khong can cai .NET SDK tren may — dung qua Docker.
set -euo pipefail
cd "$(dirname "$0")"
WORK=$(mktemp -d); trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/Properties"
cp PlayerMessage.vi.resx "$WORK/Properties/"
cat > "$WORK/sat.csproj" <<'CSPROJ'
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework>
    <AssemblyName>MUnique.OpenMU.GameLogic</AssemblyName>
    <RootNamespace>MUnique.OpenMU.GameLogic</RootNamespace>
    <EnableDefaultCompileItems>false</EnableDefaultCompileItems>
    <EnableDefaultEmbeddedResourceItems>false</EnableDefaultEmbeddedResourceItems>
    <GenerateAssemblyInfo>false</GenerateAssemblyInfo>
  </PropertyGroup>
  <ItemGroup>
    <EmbeddedResource Include="Properties/PlayerMessage.vi.resx">
      <LogicalName>MUnique.OpenMU.GameLogic.Properties.PlayerMessage.vi.resources</LogicalName>
    </EmbeddedResource>
  </ItemGroup>
</Project>
CSPROJ
docker run --rm -v "$WORK":/src -w /src mcr.microsoft.com/dotnet/sdk:10.0 \
  dotnet build -c Release -v minimal
mkdir -p vi
cp "$WORK/bin/Release/net10.0/vi/MUnique.OpenMU.GameLogic.resources.dll" vi/
echo "OK -> vi/MUnique.OpenMU.GameLogic.resources.dll"
