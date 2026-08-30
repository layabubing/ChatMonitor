#!/bin/bash
# 安装 Android SDK + JDK17 到 D:\Softwares（一次性环境搭建脚本）
set -x
SDK=/d/Softwares/AndroidSdk
DL=/d/Softwares/_dl
mkdir -p "$SDK/cmdline-tools" "$DL"
cd "$DL"

# 1. 下载 command line tools + Microsoft OpenJDK 17
[ -f cmdtools.zip ] || curl -fSL -o cmdtools.zip https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip || exit 1
[ -f jdk17.zip ] || curl -fSL -o jdk17.zip https://aka.ms/download-jdk/microsoft-jdk-17-windows-x64.zip || exit 1

# 2. 解压到规范目录 cmdline-tools/latest/
WIN_DL=$(cygpath -w "$DL")
WIN_SDK=$(cygpath -w "$SDK")
if [ ! -d "$SDK/cmdline-tools/latest" ]; then
  powershell -NoProfile -Command "Expand-Archive -Force '${WIN_DL}\\cmdtools.zip' '${WIN_DL}\\ct'" || exit 1
  mv "$DL/ct/cmdline-tools" "$SDK/cmdline-tools/latest" || exit 1
  rm -rf "$DL/ct"
fi
if ! ls /d/Softwares/jdk-17*/bin/java.exe >/dev/null 2>&1; then
  powershell -NoProfile -Command "Expand-Archive -Force '${WIN_DL}\\jdk17.zip' '${WIN_DL}'" || exit 1
fi
JDKDIR=$(ls -d /d/Softwares/jdk-17*/ | head -1)
echo "JDKDIR=$JDKDIR"
export JAVA_HOME=$(cygpath -w "$JDKDIR")

# 3. 接受许可 + 安装组件
yes | "$SDK/cmdline-tools/latest/bin/sdkmanager.bat" --sdk_root="$(cygpath -w $SDK)" --licenses >/dev/null 2>&1
"$SDK/cmdline-tools/latest/bin/sdkmanager.bat" --sdk_root="$(cygpath -w $SDK)" \
  "platform-tools" "platforms;android-36" "build-tools;36.0.0" || exit 1

echo "==== SDK 安装完成 ===="
ls "$SDK"
