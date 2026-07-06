// public/custom.js — окончательная версия с подавлением системного сайдбара, сворачиванием и скрытием логотипа Chainlit
(function() {
    console.log('[ULTIMATE] === ЗАПУСК С ОТКЛЮЧЕНИЕМ СИСТЕМНОГО САЙДБАРА И СКРЫТИЕМ ЛОГОТИПА ===');

    // === УСИЛЕННАЯ ФУНКЦИЯ: скрытие логотипа Chainlit (все возможные селекторы) ===
    const hideChainlitLogo = () => {
        // Массив всех селекторов из скриншота и дополнительные
        const logoSelectors = [
            'img[alt="logo"]',
            '.logo.w-\\[150px\\]',
            '.flex.justify-center.gap-2.md\\:justify-start',
            '#root .logo.w-\\[150px\\]',
            '#root [alt="logo"]',
            '#root div div div img',
            'div div div div img',
            '[alt="logo"]'
        ];

        logoSelectors.forEach(sel => {
            document.querySelectorAll(sel).forEach(el => {
                if (el.tagName === 'IMG' || el.classList?.contains('logo') || el.hasAttribute('alt')) {
                    // Удаляем или скрываем
                    el.style.display = 'none';
                    el.remove(); // полностью удаляем из DOM
                    console.log(`[ULTIMATE] Удалён элемент по селектору: ${sel}`);
                } else if (el.children && el.children.length > 0) {
                    // Если это контейнер с картинкой внутри, скрываем контейнер
                    el.style.display = 'none';
                    console.log(`[ULTIMATE] Скрыт контейнер по селектору: ${sel}`);
                } else {
                    el.style.display = 'none';
                }
            });
        });

        // Дополнительно: пробегаем по всем картинкам и удаляем те, у которых alt содержит "logo" или src похож на логотип Chainlit
        document.querySelectorAll('img').forEach(img => {
            const alt = (img.getAttribute('alt') || '').toLowerCase();
            const src = (img.getAttribute('src') || '').toLowerCase();
            if (alt.includes('logo') || src.includes('logo') || src.includes('chainlit')) {
                img.style.display = 'none';
                img.remove();
                console.log('[ULTIMATE] Удалена картинка логотипа по атрибутам:', alt, src);
                // Также удаляем родительский контейнер, если он мал и содержит только логотип
                const parent = img.closest('div, a, .flex');
                if (parent && parent.children.length === 1) {
                    parent.style.display = 'none';
                }
            }
        });
    };

    // 1. Удаляем/скрываем все системные сайдбары и их кнопки
    const killSystemSidebars = () => {
        const systemSidebarSelectors = [
            '[data-sidebar="rail"]',
            '[title="Toggle Sidebar"]',
            '[class*="absolute inset-y-0 z-20 hidden w-4"]',
            '[class*="-translate-x-1V"]',
            '[data-sidebar="sidebar"]',
            '.group-data-\\[collapsible\\=offcanvas\\]:-translate-x-full',
            '.group-data-\\[side\\=left\\]:-translate-x-full'
        ];
        systemSidebarSelectors.forEach(sel => {
            document.querySelectorAll(sel).forEach(el => {
                console.log('[ULTIMATE] Удаляю системный элемент:', el);
                el.remove();
            });
        });
        const possibleHamburgers = document.querySelectorAll('button[class*="hamburger"], button[aria-label*="Toggle"], button[data-sidebar]');
        possibleHamburgers.forEach(btn => {
            if (btn.id !== 'custom-hamburger') {
                console.log('[ULTIMATE] Удаляю системную кнопку:', btn);
                btn.remove();
            }
        });
        hideChainlitLogo();
    };
    killSystemSidebars();
    const systemObserver = new MutationObserver(() => killSystemSidebars());
    systemObserver.observe(document.body, { childList: true, subtree: true });

    // 2. Скрываем Readme
    const hideReadme = () => {
        const btn = document.getElementById('readme-button') || document.querySelector('button[title="Readme"], button[aria-label="Readme"]');
        if (btn) btn.style.display = 'none';
    };
    hideReadme();
    new MutationObserver(hideReadme).observe(document.body, { childList: true, subtree: true });

    // 3. Удаляем предыдущие кастомные панели
    const killOurSidebars = () => {
        document.querySelectorAll('#custom-sidebar, #custom-hamburger').forEach(el => el.remove());
    };
    killOurSidebars();

    // 4. API для истории чатов
    const API_BASE = '/history-api';
    const USER_ID = 'dev_user';

    async function fetchThreads() {
        const res = await fetch(`${API_BASE}/threads`, { headers: { 'X-User-ID': USER_ID } });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    }
    async function deleteThread(id) {
        const res = await fetch(`${API_BASE}/threads/${id}`, { method: 'DELETE', headers: { 'X-User-ID': USER_ID } });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    }

    async function displayChats(listEl) {
        if (!listEl) return;
        listEl.innerHTML = '<li>Загрузка...</li>';
        try {
            const threads = await fetchThreads();
            if (!threads || threads.length === 0) {
                listEl.innerHTML = '<li>Нет сохранённых чатов</li><li style="font-size:12px;">Новый чат добавится автоматически</li>';
                return;
            }
            listEl.innerHTML = '';
            threads.forEach(thread => {
                const li = document.createElement('li');
                li.style.cssText = 'padding: 8px; margin: 4px 0; background: #2c3e50; border-radius: 6px; cursor: pointer; display: flex; justify-content: space-between; align-items: center;';
                const nameSpan = document.createElement('span');
                nameSpan.textContent = thread.name || `Чат ${new Date(thread.created_at).toLocaleString()}`;
                nameSpan.style.flex = '1';
                nameSpan.onclick = () => location.href = `/thread/${thread.id}`;
                const delBtn = document.createElement('button');
                delBtn.textContent = '✕';
                delBtn.style.background = 'none';
                delBtn.style.border = 'none';
                delBtn.style.color = '#aaa';
                delBtn.style.cursor = 'pointer';
                delBtn.style.marginLeft = '8px';
                delBtn.onclick = async (e) => {
                    e.stopPropagation();
                    if (confirm('Удалить чат?')) {
                        await deleteThread(thread.id);
                        displayChats(listEl);
                    }
                };
                li.appendChild(nameSpan);
                li.appendChild(delBtn);
                listEl.appendChild(li);
            });
        } catch (err) {
            console.error(err);
            listEl.innerHTML = '<li>Ошибка загрузки</li>';
        }
    }

    // 5. Создаём свою панель
    const sidebar = document.createElement('div');
    sidebar.id = 'custom-sidebar';
    sidebar.style.cssText = `
        position: fixed !important;
        top: 0 !important;
        left: -280px !important;
        width: 280px !important;
        height: 100% !important;
        background-color: #1e1e2f !important;
        z-index: 10001 !important;
        transition: left 0.3s ease !important;
        box-shadow: 2px 0 10px rgba(0,0,0,0.5) !important;
        overflow-y: auto !important;
        color: white !important;
    `;
    sidebar.innerHTML = `
        <div style="padding: 20px; height: 100%; display: flex; flex-direction: column;">
            <h3 style="margin-top:0;">История чатов</h3>
            <ul id="history-list" style="list-style: none; padding: 0; flex-grow:1; overflow-y:auto;"></ul>
        </div>
    `;
    document.body.appendChild(sidebar);
    console.log('[ULTIMATE] Кастомный sidebar создан');

    // 6. Кнопка гамбургер
    const toggleBtn = document.createElement('button');
    toggleBtn.id = 'custom-hamburger';
    toggleBtn.textContent = '☰';
    toggleBtn.style.cssText = `
        position: fixed !important;
        left: 15px !important;
        top: 15px !important;
        z-index: 10002 !important;
        background: #2c3e50 !important;
        color: white !important;
        border: none !important;
        font-size: 24px !important;
        padding: 6px 14px !important;
        border-radius: 8px !important;
        cursor: pointer !important;
        box-shadow: 0 2px 5px rgba(0,0,0,0.2) !important;
    `;
    document.body.appendChild(toggleBtn);

    let isOpen = false;
    const listContainer = document.getElementById('history-list');

    const setSidebarState = (open) => {
        sidebar.style.left = open ? '0px' : '-280px';
        console.log(`[ULTIMATE] Панель ${open ? 'открыта' : 'закрыта'}`);
    };

    toggleBtn.onclick = (e) => {
        e.stopPropagation();
        e.preventDefault();
        isOpen = !isOpen;
        setSidebarState(isOpen);
        toggleBtn.textContent = isOpen ? '✖' : '☰';
        if (isOpen) displayChats(listContainer);
    };

    document.addEventListener('click', (e) => {
        if (isOpen && !sidebar.contains(e.target) && e.target !== toggleBtn && !toggleBtn.contains(e.target)) {
            isOpen = false;
            setSidebarState(false);
            toggleBtn.textContent = '☰';
        }
    });

    setInterval(() => {
        const ourSidebars = document.querySelectorAll('#custom-sidebar');
        if (ourSidebars.length > 1) for (let i = 1; i < ourSidebars.length; i++) ourSidebars[i].remove();
        const ourBtns = document.querySelectorAll('#custom-hamburger');
        if (ourBtns.length > 1) for (let i = 1; i < ourBtns.length; i++) ourBtns[i].remove();
        killSystemSidebars();
        hideChainlitLogo();
    }, 2000);

    setTimeout(hideChainlitLogo, 100);
    console.log('[ULTIMATE] Готово. Системный сайдбар подавлен, логотип должен быть скрыт.');
})();
