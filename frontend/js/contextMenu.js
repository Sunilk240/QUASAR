/**
 * QUASAR - Context Menu System
 */

class ContextMenu {
    constructor() {
        this.menu = null;
        this.init();
    }

    init() {
        this.menu = document.createElement('div');
        this.menu.className = 'context-menu';
        this.menu.style.display = 'none';
        document.body.appendChild(this.menu);

        // Hide menu on click outside
        document.addEventListener('click', () => this.hide());
        document.addEventListener('contextmenu', () => this.hide());
        window.addEventListener('blur', () => this.hide());
    }

    /**
     * Show context menu at specific coordinates
     * @param {number} x - X coordinate
     * @param {number} y - Y coordinate
     * @param {Array} items - Array of { label, icon, action, separator, danger }
     */
    show(x, y, items) {
        this.menu.innerHTML = '';

        items.forEach(item => {
            if (item.separator) {
                const sep = document.createElement('div');
                sep.className = 'context-menu-separator';
                this.menu.appendChild(sep);
                return;
            }

            const div = document.createElement('div');
            div.className = `context-menu-item ${item.danger ? 'danger' : ''}`;

            const iconHtml = item.icon ? `<i data-lucide="${item.icon}"></i>` : '<span class="icon-placeholder"></span>';

            div.innerHTML = `
                ${iconHtml}
                <span class="label">${item.label}</span>
                ${item.shortcut ? `<span class="shortcut">${item.shortcut}</span>` : ''}
            `;

            div.addEventListener('click', (e) => {
                e.stopPropagation();
                this.hide();
                item.action();
            });

            this.menu.appendChild(div);
        });

        // Initialize icons
        if (window.lucide) lucide.createIcons();

        // Position menu
        this.menu.style.display = 'block';

        // Prevent overflow
        const rect = this.menu.getBoundingClientRect();
        const winWidth = window.innerWidth;
        const winHeight = window.innerHeight;

        let finalX = x;
        let finalY = y;

        if (x + rect.width > winWidth) finalX = x - rect.width;
        if (y + rect.height > winHeight) finalY = y - rect.height;

        this.menu.style.left = `${finalX}px`;
        this.menu.style.top = `${finalY}px`;
    }

    hide() {
        if (this.menu) {
            this.menu.style.display = 'none';
        }
    }
}

// Global instance
window.contextMenu = new ContextMenu();
