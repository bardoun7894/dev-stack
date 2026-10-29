#!/bin/bash
# bash tests/test_server_first_warn.sh — hooks/server-first-warn.sh (G21): SessionStart warns on Mac for website repos
H="$(cd "$(dirname "$0")/.." && pwd)/hooks/server-first-warn.sh"
T=$(mktemp -d); fails=0

mkdir -p "$T/bin-darwin" "$T/bin-linux"
printf '#!/bin/sh\necho Darwin\n' > "$T/bin-darwin/uname"
printf '#!/bin/sh\necho Linux\n' > "$T/bin-linux/uname"
chmod +x "$T/bin-darwin/uname" "$T/bin-linux/uname"

mkrepo() { # name
  mkdir -p "$T/repos/$1"
  git -C "$T/repos/$1" init -q
}

check_warn() { # name dir
  local out rc
  out=$(printf '{"cwd":"%s"}' "$2" | PATH="$T/bin-darwin:$PATH" "$H" 2>/dev/null); rc=$?
  if [ "$rc" = 0 ] && printf '%s' "$out" | grep -q '"hookEventName"[[:space:]]*:[[:space:]]*"SessionStart"' && printf '%s' "$out" | grep -q 'SERVER-FIRST:'; then
    echo "ok   $1"
  else
    echo "FAIL $1 (rc=$rc, want SERVER-FIRST warn) out=$out"
    fails=1
  fi
}

check_silent() { # name dir [os]
  local os="${3:-darwin}" out rc
  out=$(printf '{"cwd":"%s"}' "$2" | PATH="$T/bin-$os:$PATH" "$H" 2>/dev/null); rc=$?
  if [ "$rc" = 0 ] && [ -z "$out" ]; then
    echo "ok   $1"
  else
    echo "FAIL $1 (rc=$rc, want silent) out=$out"
    fails=1
  fi
}

# 1. Website repos on Darwin -> warn
mkrepo next-site
printf '{"dependencies":{"next":"14.0.0","react":"18.0.0"}}\n' > "$T/repos/next-site/package.json"
mkdir -p "$T/repos/next-site/src/pages"
check_warn next-root "$T/repos/next-site"
check_warn next-subdir "$T/repos/next-site/src/pages"

mkrepo vite-site
printf '{"devDependencies":{"vite":"^5.0.0"}}\n' > "$T/repos/vite-site/package.json"
check_warn vite-site "$T/repos/vite-site"

mkrepo laravel-site
printf '{"require":{"php":"^8.2","laravel/framework":"^11.0"}}\n' > "$T/repos/laravel-site/composer.json"
check_warn laravel-site "$T/repos/laravel-site"

mkrepo monorepo-frontend
mkdir -p "$T/repos/monorepo-frontend/frontend" "$T/repos/monorepo-frontend/backend"
printf '{"dependencies":{"next":"14.0.0","react":"18.0.0"}}\n' > "$T/repos/monorepo-frontend/frontend/package.json"
check_warn monorepo-frontend "$T/repos/monorepo-frontend"

mkrepo monorepo-mobile-sub
mkdir -p "$T/repos/monorepo-mobile-sub/app"
printf 'name: mobile_sub\n' > "$T/repos/monorepo-mobile-sub/app/pubspec.yaml"
check_silent monorepo-mobile-sub "$T/repos/monorepo-mobile-sub"

# 2. Linux no-op via PATH uname shim
check_silent linux-noop "$T/repos/next-site" linux

# 3. Mobile / desktop / Mac / overridden repos -> silent
mkrepo flutter-app
printf 'name: my_app\n' > "$T/repos/flutter-app/pubspec.yaml"
printf '{"dependencies":{"react-dom":"18.0.0"}}\n' > "$T/repos/flutter-app/package.json"
check_silent flutter-app "$T/repos/flutter-app"

mkrepo ios-xcode
mkdir -p "$T/repos/ios-xcode/App.xcodeproj"
printf '{"dependencies":{"vite":"5.0.0"}}\n' > "$T/repos/ios-xcode/package.json"
check_silent ios-xcode "$T/repos/ios-xcode"

mkrepo swift-pkg
printf '// swift-tools-version:5.9\n' > "$T/repos/swift-pkg/Package.swift"
check_silent swift-pkg "$T/repos/swift-pkg"

mkrepo rn-mobile
mkdir -p "$T/repos/rn-mobile/android" "$T/repos/rn-mobile/ios"
printf '{"dependencies":{"react-dom":"18.0.0"}}\n' > "$T/repos/rn-mobile/package.json"
check_silent rn-mobile "$T/repos/rn-mobile"

mkrepo electron-app
printf '{"dependencies":{"react-dom":"18.0.0"},"devDependencies":{"electron":"^28.0.0"}}\n' > "$T/repos/electron-app/package.json"
check_silent electron-app "$T/repos/electron-app"

mkrepo tauri-app
printf '{"dependencies":{"vite":"^5.0.0","@tauri-apps/api":"^2.0.0"}}\n' > "$T/repos/tauri-app/package.json"
check_silent tauri-app "$T/repos/tauri-app"

mkrepo where-to-work-local
printf '{"dependencies":{"next":"14.0.0"}}\n' > "$T/repos/where-to-work-local/package.json"
printf 'local\n' > "$T/repos/where-to-work-local/.where-to-work"
check_silent where-to-work-local "$T/repos/where-to-work-local"

mkrepo cli-tool
printf '{"dependencies":{"commander":"^11.0.0"}}\n' > "$T/repos/cli-tool/package.json"
check_silent cli-tool "$T/repos/cli-tool"

# 4. Malformed input in non-website dir -> silent exit 0
out=$(cd "$T" && printf 'not-json' | PATH="$T/bin-darwin:$PATH" "$H" 2>/dev/null); rc=$?
[ "$rc" = 0 ] && [ -z "$out" ] && echo "ok   malformed-input" || { echo "FAIL malformed-input (rc=$rc, out=$out)"; fails=1; }

rm -rf "$T"; exit $fails
