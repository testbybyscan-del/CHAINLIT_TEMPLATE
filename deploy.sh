#!/bin/bash
# ============================================================
# @Bybyscan
# deploy.sh – автоматический деплой новой версии Чат-бота на базе Chainlit
# Версия: 0.2.1
# Дата: 06.07.2026
#
# Особенности:
#   - Интерактивный выбор порта (по умолчанию 443)
#   - Автоматическая генерация .env и roles.json (дефолтный промпт)
#   - Очистка старых версий (--clean)
#   - Указание количества сохраняемых версий (--keep N)
#   - Принудительная сборка образа (--build)
#   - Манифест (.deploy_manifest) с информацией о ресурсах
#   - Удаление конкретной версии (--remove N)
#   - Просмотр списка версий (--list)
#   - Автоопределение порта аудио-транскрипции
#   - Безопасное освобождение занятого порта (--force)
# ============================================================

set -e

# ------------------- Конфигурация -------------------
BASE_DIR="/home/docker-containers" # УКАЖИТЕ ВЕРНЫЙ ПУТЬ!!!
TEMPLATE_DIR="$BASE_DIR/CHAINLIT_TEMPLATE"
PROJECT_PREFIX="CHAINLIT_DEV"
DEFAULT_PORT="443"
DEFAULT_KEEP=3
MANIFEST_FILENAME=".deploy_manifest"

CLEAN_MODE=false
KEEP_VERSIONS=$DEFAULT_KEEP
CUSTOM_PORT=""
REMOVE_VERSION=""
LIST_MODE=false
FORCE_MODE=false
BUILD_MODE=false

# ------------------- Обработка аргументов -------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --clean) CLEAN_MODE=true ;;
        --keep) KEEP_VERSIONS="$2"; shift ;;
        --port) CUSTOM_PORT="$2"; shift ;;
        --remove) REMOVE_VERSION="$2"; shift ;;
        --list) LIST_MODE=true ;;
        --force) FORCE_MODE=true ;;
        --build) BUILD_MODE=true ;;
        *) echo "❌ Неизвестный аргумент: $1"; exit 1 ;;
    esac
    shift
done

# ------------------- Вспомогательные функции -------------------

check_port_busy() {
    local port=$1
    ss -tuln | grep -q ":${port}\b"
}

stop_container_on_port() {
    local port=$1
    local container_id=$(docker ps --filter "publish=${port}" --format "{{.ID}}" | head -1)
    if [ -n "$container_id" ]; then
        local container_name=$(docker inspect --format '{{.Name}}' "$container_id" | sed 's/^\///')
        echo "🔍 Найден контейнер, занимающий порт $port: $container_name"
        if [[ "$port" == "443" ]] && [[ "$container_name" == *"nginx-transcriber"* ]]; then
            echo "⚠️ Это ваш текущий nginx для транскрипции."
            if [ "$FORCE_MODE" = true ]; then
                echo "⚡ Режим --force: остановка без подтверждения."
                docker stop "$container_id" && docker rm "$container_id"
                echo "✅ Контейнер удалён."
                return 0
            else
                read -p "Остановить и удалить его? Новый Chainlit займёт порт 443. (y/N): " -n 1 -r
                echo
                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    docker stop "$container_id" && docker rm "$container_id"
                    echo "✅ Контейнер удалён."
                    return 0
                else
                    echo "❌ Отказ от остановки. Порт остаётся занят."
                    return 1
                fi
            fi
        else
            if [ "$FORCE_MODE" = true ]; then
                echo "⚡ Режим --force: остановка без подтверждения."
                docker stop "$container_id" && docker rm "$container_id"
                echo "✅ Контейнер удалён."
                return 0
            else
                read -p "Остановить и удалить его? (y/N): " -n 1 -r
                echo
                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    docker stop "$container_id" && docker rm "$container_id"
                    echo "✅ Контейнер удалён."
                    return 0
                else
                    echo "❌ Отказ от остановки. Порт остаётся занят."
                    return 1
                fi
            fi
        fi
    else
        echo "❌ Не удалось определить контейнер для порта $port."
        return 1
    fi
}

get_port() {
    local default_port=$1
    local chosen_port

    if [ -n "$CUSTOM_PORT" ]; then
        chosen_port="$CUSTOM_PORT"
    else
        echo "Введите порт для новой версии (по умолчанию $default_port):" >&2
        read -p "" chosen_port
        [ -z "$chosen_port" ] && chosen_port="$default_port"
    fi

    if ! [[ "$chosen_port" =~ ^[0-9]+$ ]]; then
        echo "❌ Некорректный порт. Использую по умолчанию: $default_port" >&2
        chosen_port="$default_port"
    fi

    if check_port_busy "$chosen_port"; then
        echo "⚠️ Порт $chosen_port уже занят." >&2
        if [ "$FORCE_MODE" = true ]; then
            echo "⚡ Режим --force: попытка автоматически освободить порт..."
            if stop_container_on_port "$chosen_port"; then
                echo "✅ Порт освобождён. Продолжаю." >&2
            else
                echo "❌ Не удалось освободить порт. Завершение." >&2
                exit 1
            fi
        else
            read -p "Остановить процесс, занимающий порт? (y/N): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                if stop_container_on_port "$chosen_port"; then
                    echo "✅ Порт освобождён. Продолжаю." >&2
                else
                    echo "❌ Не удалось освободить порт. Завершение." >&2
                    exit 1
                fi
            else
                echo "❌ Порт занят. Завершение." >&2
                exit 1
            fi
        fi
    fi

    echo "$chosen_port"
}

# ------------------- Функции манифеста -------------------

create_manifest() {
    local project_dir="$1"
    local project_name="$2"
    local nginx_port="$3"
    local manifest_path="$project_dir/$MANIFEST_FILENAME"

    local postgres_volume="${project_name}-postgres-data"
    local ollama_volume="${project_name}-ollama-data"
    local network_name="${project_name}_default"
    local chainlit_image="chainlit-app:${project_name}"
    local history_api_image="${project_name}-history-api"

    cat > "$manifest_path" <<EOF
# Манифест развёрнутой версии Chainlit
# Создан: $(date '+%Y-%m-%d %H:%M:%S')
PROJECT_NAME=$project_name
NGINX_PORT=$nginx_port
POSTGRES_VOLUME=$postgres_volume
OLLAMA_VOLUME=$ollama_volume
NETWORK=$network_name
CHAINLIT_IMAGE=$chainlit_image
HISTORY_API_IMAGE=$history_api_image
# Для полного удаления выполните из папки проекта:
#   docker compose -p $project_name down -v --rmi all
#   rm -rf $project_dir
EOF

    echo "📄 Манифест сохранён: $manifest_path"
}

# ------------------- Функции управления версиями -------------------

remove_version_by_name() {
    local project_name="$1"
    local project_dir="$BASE_DIR/${PROJECT_PREFIX}_${project_name#${PROJECT_PREFIX}_}"

    if [[ "$project_name" =~ ^[0-9]+$ ]]; then
        project_name="${PROJECT_PREFIX}_$project_name"
    fi

    if [ -z "$project_dir" ] || [ ! -d "$project_dir" ]; then
        local found_dir=$(find "$BASE_DIR" -maxdepth 1 -type d -name "${project_name}" 2>/dev/null | head -1)
        if [ -n "$found_dir" ]; then
            project_dir="$found_dir"
        else
            echo "❌ Не найдена папка для проекта $project_name"
            return 1
        fi
    fi

    echo "🗑️ Удаление версии $project_name (папка $project_dir)"

    if [ -f "$project_dir/docker-compose.yml" ] || [ -f "$project_dir/docker-compose.yaml" ]; then
        cd "$project_dir"
        echo "🧹 Остановка и удаление контейнеров, томов, сети, образов..."
        docker compose -p "$project_name" down -v --rmi all 2>/dev/null || true
        cd "$BASE_DIR"
    else
        echo "⚠️ В папке нет compose-файла, пропускаю остановку."
    fi

    rm -rf "$project_dir"
    echo "✅ Папка $project_dir удалена."
}

list_versions() {
    echo "📋 Список развёрнутых версий:"
    local count=0
    for dir in "$BASE_DIR"/${PROJECT_PREFIX}_[0-9]*; do
        if [ -d "$dir" ]; then
            local manifest="$dir/$MANIFEST_FILENAME"
            local version_name=$(basename "$dir")
            local port=""
            local created=""
            if [ -f "$manifest" ]; then
                port=$(grep '^NGINX_PORT=' "$manifest" | cut -d'=' -f2)
                created=$(grep '^# Создан:' "$manifest" | sed 's/^# Создан: //')
            else
                if [ -f "$dir/.env" ]; then
                    port=$(grep '^NGINX_PORT=' "$dir/.env" | cut -d'=' -f2)
                fi
                created="(манифест отсутствует)"
            fi
            echo "  $version_name → порт ${port:-?}, создан $created"
            ((count++))
        fi
    done
    if [ $count -eq 0 ]; then
        echo "  (нет версий)"
    fi
}

cleanup_old_versions() {
    local keep=$1
    [ -z "$keep" ] && keep=$KEEP_VERSIONS

    cd "$BASE_DIR" || exit 1

    local all_versions=()
    while IFS= read -r dir; do
        all_versions+=("$dir")
    done < <(ls -d ${PROJECT_PREFIX}_* 2>/dev/null | grep -E "${PROJECT_PREFIX}_[0-9]+$" | sort -V)

    local total=${#all_versions[@]}
    if [ $total -le $keep ]; then
        echo "✅ Уже оставлено $total версий (не более $keep). Очистка не требуется."
        return 0
    fi

    local to_delete=()
    local count=0
    for dir in "${all_versions[@]}"; do
        if [ $count -ge $((total - keep)) ]; then
            break
        fi
        to_delete+=("$dir")
        ((count++))
    done

    echo "🧹 Будет удалено ${#to_delete[@]} старых версий:"
    printf '  %s\n' "${to_delete[@]}"

    if [ "$FORCE_MODE" = false ] && [ -z "$CUSTOM_PORT" ] && [ -z "$REMOVE_VERSION" ]; then
        read -p "Продолжить удаление? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "❌ Очистка отменена."
            return 1
        fi
    fi

    for dir in "${to_delete[@]}"; do
        remove_version_by_name "$dir"
    done

    echo "🧹 Удаляю неиспользуемые Docker-образы (общие)..."
    docker image prune -f

    echo "✅ Очистка завершена. Оставлено $keep последних версий."
}

# ------------------- Основная логика -------------------

if [ "$LIST_MODE" = true ]; then
    list_versions
    exit 0
fi

if [ -n "$REMOVE_VERSION" ]; then
    remove_version_by_name "$REMOVE_VERSION"
    exit 0
fi

if [ "$CLEAN_MODE" = true ] && [ -z "$CUSTOM_PORT" ]; then
    echo "🧹 Запуск очистки старых версий (оставляем последние $KEEP_VERSIONS)..."
    cleanup_old_versions "$KEEP_VERSIONS"
    exit 0
fi

# ------------------- Деплой новой версии -------------------
cd "$BASE_DIR"

LAST_VERSION=$(ls -d ${PROJECT_PREFIX}_* 2>/dev/null | grep -E "${PROJECT_PREFIX}_[0-9]+$" | sed "s/${PROJECT_PREFIX}_//" | sort -n | tail -1)
if [ -z "$LAST_VERSION" ]; then
    NEXT_VERSION=1
else
    NEXT_VERSION=$((LAST_VERSION + 1))
fi

NEW_DIR="${BASE_DIR}/${PROJECT_PREFIX}_${NEXT_VERSION}"
echo "📁 Создаю новую версию: ${PROJECT_PREFIX}_${NEXT_VERSION}"

if [ ! -d "$TEMPLATE_DIR" ]; then
    echo "❌ Ошибка: шаблон '$TEMPLATE_DIR' не найден."
    exit 1
fi

cp -r "$TEMPLATE_DIR" "$NEW_DIR"
echo "✅ Шаблон скопирован в $NEW_DIR"

if [ -f "$NEW_DIR/cert.pem" ] && [ -f "$NEW_DIR/key.pem" ]; then
    mkdir -p "$NEW_DIR/certs"
    cp "$NEW_DIR/cert.pem" "$NEW_DIR/key.pem" "$NEW_DIR/certs/"
    echo "✅ Сертификаты скопированы в $NEW_DIR/certs/"
fi

CHOSEN_PORT=$(get_port "$DEFAULT_PORT")

# ------------------- Генерация .env -------------------
PROJECT_NAME_LOWER="chainlit-dev-${NEXT_VERSION}"
if command -v openssl &> /dev/null; then
    AUTH_SECRET=$(openssl rand -hex 32)
    DB_PASSWORD=$(openssl rand -hex 24)
else
    AUTH_SECRET="change_me_$(date +%s)"
    DB_PASSWORD="strong_password_here"
fi

AUDIO_PORT=$(docker port audio-transcriber-api 9090 2>/dev/null | sed -n 's/.*:\([0-9]*\)$/\1/p' | head -1)
if [ -z "$AUDIO_PORT" ]; then
    AUDIO_PORT=9090
    echo "⚠️ Не удалось определить порт audio-transcriber-api, использую 9090 по умолчанию."
fi
AUDIO_URL="http://host.docker.internal:${AUDIO_PORT}/api/v1/transcribe"

cat > "$NEW_DIR/.env" <<EOF
# Автоматически сгенерировано скриптом deploy.sh (v0.2.1)
PROJECT_NAME=$PROJECT_NAME_LOWER
NGINX_PORT=$CHOSEN_PORT
CHAINLIT_AUTH_SECRET=$AUTH_SECRET
POSTGRES_PASSWORD=$DB_PASSWORD
ASSISTANT_ROLE=assistant
ROLES_FILE=roles.json
AUDIO_TRANSCRIBER_API_URL=$AUDIO_URL
EOF

echo "✅ Создан .env с PROJECT_NAME=$PROJECT_NAME_LOWER, NGINX_PORT=$CHOSEN_PORT"
echo "   AUDIO_TRANSCRIBER_API_URL=$AUDIO_URL"
echo "   ASSISTANT_ROLE=assistant (дефолтный промпт)"

# ------------------- Создание roles.json (дефолтный промпт) -------------------
cat > "$NEW_DIR/roles.json" <<'EOF'
{
  "assistant": "Ты — полезный AI-ассистент. Отвечай на вопросы ясно, точно и дружелюбно. Если не знаешь ответа, честно скажи об этом. Помогай пользователю решать задачи, давай советы и пояснения."
}
EOF

echo "✅ Создан файл roles.json с дефолтным системным промптом."

# ------------------- Запуск контейнеров -------------------
cd "$NEW_DIR"
echo "🚀 Запускаю контейнеры..."

if [ "$BUILD_MODE" = true ] || ! docker images -q "chainlit-app:${PROJECT_NAME_LOWER}" &>/dev/null; then
    echo "🔨 Сборка образа chainlit-app:${PROJECT_NAME_LOWER}..."
    docker compose -p "$PROJECT_NAME_LOWER" build
else
    echo "✅ Образ chainlit-app:${PROJECT_NAME_LOWER} уже существует, сборка пропущена (используйте --build для принудительной пересборки)."
fi

docker compose -p "$PROJECT_NAME_LOWER" up -d

if [ $? -eq 0 ]; then
    echo "✅ Развёрнута версия ${PROJECT_PREFIX}_${NEXT_VERSION} (проект $PROJECT_NAME_LOWER)"
    echo "🌐 Доступно по HTTPS на порту $CHOSEN_PORT (например, https://ваш-сервер:$CHOSEN_PORT)"
    echo "📝 Логи: docker compose -p $PROJECT_NAME_LOWER logs -f"
    create_manifest "$NEW_DIR" "$PROJECT_NAME_LOWER" "$CHOSEN_PORT"
else
    echo "❌ Ошибка при запуске Compose"
    exit 1
fi

if [ "$CLEAN_MODE" = true ]; then
    echo ""
    echo "🧹 Запуск очистки старых версий (оставляем последние $KEEP_VERSIONS)..."
    cleanup_old_versions "$KEEP_VERSIONS"
fi

echo "🎉 Готово!"
