/**
 * QUASAR - Toast Notification System
 * Non-intrusive user feedback notifications
 */

class ToastManager {
    constructor() {
        this.container = null;
        this.toasts = [];
        this.maxToasts = 5;
        this.defaultDuration = 4000; // 4 seconds
        this.init();
    }

    /**
     * Initialize toast container
     */
    init() {
        // Create container if it doesn't exist
        this.container = document.getElementById('toastContainer');
        if (!this.container) {
            this.container = document.createElement('div');
            this.container.id = 'toastContainer';
            this.container.className = 'toast-container';
            document.body.appendChild(this.container);
        }
    }

    /**
     * Show a toast notification
     * @param {string} message - The message to display
     * @param {string} type - Type: 'success', 'error', 'warning', 'info'
     * @param {object} options - Additional options
     */
    show(message, type = 'info', options = {}) {
        const {
            duration = this.defaultDuration,
            dismissible = true,
            icon = null,
            action = null
        } = options;

        // Create toast element
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;

        // Get icon based on type
        const iconName = icon || this.getIconForType(type);

        toast.innerHTML = `
            <div class="toast-icon">
                <i data-lucide="${iconName}"></i>
            </div>
            <div class="toast-content">
                <span class="toast-message">${this.escapeHtml(message)}</span>
            </div>
            ${action ? `<button class="toast-action">${action.label}</button>` : ''}
            ${dismissible ? `<button class="toast-close"><i data-lucide="x"></i></button>` : ''}
            <div class="toast-progress">
                <div class="toast-progress-bar" style="animation-duration: ${duration}ms"></div>
            </div>
        `;

        // Add to container
        this.container.appendChild(toast);
        this.toasts.push(toast);

        // Initialize lucide icons
        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }

        // Trigger animation
        requestAnimationFrame(() => {
            toast.classList.add('toast-visible');
        });

        // Setup event handlers
        if (dismissible) {
            const closeBtn = toast.querySelector('.toast-close');
            closeBtn?.addEventListener('click', () => this.dismiss(toast));
        }

        if (action) {
            const actionBtn = toast.querySelector('.toast-action');
            actionBtn?.addEventListener('click', () => {
                action.callback?.();
                this.dismiss(toast);
            });
        }

        // Auto-dismiss
        if (duration > 0) {
            setTimeout(() => this.dismiss(toast), duration);
        }

        // Limit max toasts
        while (this.toasts.length > this.maxToasts) {
            this.dismiss(this.toasts[0]);
        }

        return toast;
    }

    /**
     * Dismiss a toast
     */
    dismiss(toast) {
        if (!toast || !toast.parentNode) return;

        toast.classList.remove('toast-visible');
        toast.classList.add('toast-hiding');

        setTimeout(() => {
            toast.remove();
            this.toasts = this.toasts.filter(t => t !== toast);
        }, 300);
    }

    /**
     * Clear all toasts
     */
    clearAll() {
        [...this.toasts].forEach(toast => this.dismiss(toast));
    }

    /**
     * Get icon for toast type
     */
    getIconForType(type) {
        const icons = {
            success: 'check-circle',
            error: 'x-circle',
            warning: 'alert-triangle',
            info: 'info'
        };
        return icons[type] || 'info';
    }

    /**
     * Escape HTML to prevent XSS
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Convenience methods
    success(message, options = {}) {
        return this.show(message, 'success', options);
    }

    error(message, options = {}) {
        return this.show(message, 'error', { duration: 6000, ...options });
    }

    warning(message, options = {}) {
        return this.show(message, 'warning', options);
    }

    info(message, options = {}) {
        return this.show(message, 'info', options);
    }
}

// Create global instance
window.toast = new ToastManager();
