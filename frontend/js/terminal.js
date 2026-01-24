/**
 * AI Code Editor - Terminal Module
 * Handles multiple xterm.js terminal instances with WebSocket connections
 */

class TerminalManager {
    constructor() {
        this.terminals = new Map(); // id -> { id, name, terminal, fitAddon, websocket, isConnected, reconnectAttempts }
        this.activeTerminalId = null;
        this.terminalCount = 0;
        this.isCollapsed = false;
        this.maxReconnectAttempts = 5;
    }

    /**
     * Initialize the terminal manager
     */
    init() {
        this.setupGlobalEventListeners();

        // Create the first terminal
        this.createNewTerminal();
    }

    /**
     * Create a new terminal instance
     */
    createNewTerminal() {
        const id = `term-${Date.now()}`;
        const name = `Terminal ${++this.terminalCount}`;
        const mainContainer = document.getElementById('terminalContainer');

        // Create container for this specific terminal
        const container = document.createElement('div');
        container.id = `container-${id}`;
        container.className = 'terminal-instance';
        container.style.height = '100%';
        mainContainer.appendChild(container);

        // Create terminal instance
        const terminal = new Terminal({
            ...CONFIG.TERMINAL,
            cols: 80,
            rows: 10,
            cursorBlink: true
        });

        // Create fit addon
        const fitAddon = new FitAddon.FitAddon();
        terminal.loadAddon(fitAddon);

        // Open terminal in its container
        terminal.open(container);

        const terminalData = {
            id,
            name,
            terminal,
            fitAddon,
            websocket: null,
            isConnected: false,
            reconnectAttempts: 0
        };

        this.terminals.set(id, terminalData);

        // Switch to the new terminal
        this.switchTerminal(id);

        // Setup terminal individual listeners
        terminal.onData(data => this.sendToWebSocket(data, id));

        // Write initial message
        this.writeWelcome(terminal);

        // Connect WebSocket
        this.connectWebSocket(id);

        // Update tabs
        this.renderTabs();

        return id;
    }

    /**
     * Switch to a specific terminal
     */
    switchTerminal(id) {
        if (!this.terminals.has(id)) return;

        // Hide current active terminal
        if (this.activeTerminalId) {
            const currentContainer = document.getElementById(`container-${this.activeTerminalId}`);
            if (currentContainer) currentContainer.style.display = 'none';
        }

        // Show new active terminal
        const newContainer = document.getElementById(`container-${id}`);
        if (newContainer) newContainer.style.display = 'block';

        this.activeTerminalId = id;

        // Update tabs UI
        this.renderTabs();

        // Fit the terminal
        setTimeout(() => this.fit(id), 0);

        // Focus the terminal
        this.terminals.get(id).terminal.focus();
    }

    /**
     * Close a terminal instance
     */
    closeTerminal(id) {
        const data = this.terminals.get(id);
        if (!data) return;

        // Don't close if it's the last one (or create a new one after)
        if (this.terminals.size === 1) {
            this.createNewTerminal();
        }

        // Close WebSocket
        if (data.websocket) {
            data.websocket.onclose = null;
            data.websocket.close();
        }

        // Dispose terminal
        data.terminal.dispose();

        // Remove container
        const container = document.getElementById(`container-${id}`);
        if (container) container.remove();

        // Remove from list
        this.terminals.delete(id);

        // If it was active, switch to another
        if (this.activeTerminalId === id) {
            const nextId = Array.from(this.terminals.keys())[0];
            this.switchTerminal(nextId);
        } else {
            this.renderTabs();
        }
    }

    /**
     * Connect a terminal to its WebSocket
     */
    connectWebSocket(id) {
        const data = this.terminals.get(id);
        if (!data) return;

        // Close existing if any
        if (data.websocket) {
            data.websocket.onclose = null;
            data.websocket.close();
            data.websocket = null;
        }

        data.terminal.writeln('\x1b[33m🔄 Connecting to terminal...\x1b[0m');

        const wsUrl = CONFIG.API_BASE_URL.replace('http', 'ws') + '/terminal/ws/terminal';

        try {
            data.websocket = new WebSocket(wsUrl);

            data.websocket.onopen = () => {
                data.isConnected = true;
                data.reconnectAttempts = 0;
                console.log(`✅ Terminal ${id} connected`);
                // Clear the connecting message
                data.terminal.write('\r\x1b[K'); // Carriage return and clear line
            };

            data.websocket.onmessage = (event) => {
                data.terminal.write(event.data);
            };

            data.websocket.onclose = () => {
                data.isConnected = false;
                console.log(`🔌 Terminal ${id} disconnected`);

                if (data.reconnectAttempts < this.maxReconnectAttempts) {
                    data.reconnectAttempts++;
                    setTimeout(() => this.connectWebSocket(id), 2000);
                }
            };

            data.websocket.onerror = (error) => {
                console.error(`Terminal ${id} WebSocket error:`, error);
            };

        } catch (error) {
            console.error(`Failed to connect WebSocket for ${id}:`, error);
        }
    }

    /**
     * Send data to terminal's WebSocket
     */
    sendToWebSocket(data, id = this.activeTerminalId) {
        const terminalData = this.terminals.get(id);
        if (terminalData && terminalData.websocket && terminalData.isConnected) {
            terminalData.websocket.send(data);
        }
    }

    /**
     * Run a command (public API)
     */
    runCommand(command, id = this.activeTerminalId) {
        const data = this.terminals.get(id);
        if (!data) return;

        if (!data.isConnected) {
            this.connectWebSocket(id);
            // We could buffer it, but simpler to just try reconnecting
            return;
        }

        this.sendToWebSocket(command + '\r', id);
    }

    /**
     * Change directory
     */
    changeDirectory(path, id = this.activeTerminalId) {
        this.runCommand(`cd "${path}"`, id);
        // Show brief notification but don't spam if many terminals
        if (id === this.activeTerminalId) {
            window.toast?.info(`Syncing terminal to: ${path.split(/[\\/]/).pop()}`);
        }
    }

    /**
     * Write welcome message to a terminal
     */
    writeWelcome(terminal) {
        terminal.writeln('\x1b[1;36m╔════════════════════════════════════════╗\x1b[0m');
        terminal.writeln('\x1b[1;36m║\x1b[0m   \x1b[1;33mAI Code Editor Terminal\x1b[0m              \x1b[1;36m║\x1b[0m');
        terminal.writeln('\x1b[1;36m╚════════════════════════════════════════╝\x1b[0m');
        terminal.writeln('');
    }

    /**
     * Render terminal tabs in the header
     */
    renderTabs() {
        const tabsContainer = document.getElementById('terminalTabs');
        if (!tabsContainer) return;

        tabsContainer.innerHTML = '';

        this.terminals.forEach((data, id) => {
            const tab = document.createElement('div');
            tab.className = `terminal-tab ${id === this.activeTerminalId ? 'active' : ''}`;
            tab.dataset.id = id;

            tab.innerHTML = `
                <i data-lucide="terminal"></i>
                <span class="tab-label">${data.name}</span>
                <span class="terminal-tab-close" title="Close Terminal">
                    <i data-lucide="x"></i>
                </span>
            `;

            tab.addEventListener('click', (e) => {
                if (!e.target.closest('.terminal-tab-close')) {
                    this.switchTerminal(id);
                }
            });

            tab.querySelector('.terminal-tab-close').addEventListener('click', (e) => {
                e.stopPropagation();
                this.closeTerminal(id);
            });

            tabsContainer.appendChild(tab);
        });

        if (window.lucide) {
            lucide.createIcons();
        }
    }

    /**
     * Fit terminal to container
     */
    fit(id = this.activeTerminalId) {
        const data = this.terminals.get(id);
        if (data && data.fitAddon && !this.isCollapsed) {
            try {
                data.fitAddon.fit();
            } catch (e) {
                // Ignore fit errors
            }
        }
    }

    /**
     * Toggle terminal visibility
     */
    toggle() {
        const wrapper = document.getElementById('terminalWrapper');
        const toggleBtn = document.getElementById('toggleTerminalBtn');

        this.isCollapsed = !this.isCollapsed;
        wrapper.classList.toggle('collapsed', this.isCollapsed);

        const icon = toggleBtn.querySelector('[data-lucide]');
        if (icon) {
            icon.setAttribute('data-lucide', this.isCollapsed ? 'chevron-up' : 'chevron-down');
            lucide.createIcons();
        }

        setTimeout(() => {
            window.editorManager?.layout();
            if (!this.isCollapsed) {
                this.fit(this.activeTerminalId);
            }
        }, 100);
    }

    /**
     * Setup global event listeners
     */
    setupGlobalEventListeners() {
        // New terminal button
        document.getElementById('newTerminalBtn')?.addEventListener('click', () => {
            this.createNewTerminal();
        });

        // Clear button (clears active terminal)
        document.getElementById('clearTerminalBtn')?.addEventListener('click', () => {
            const data = this.terminals.get(this.activeTerminalId);
            if (data) {
                data.terminal.clear();
                if (data.isConnected) data.websocket.send('clear\r');
            }
        });

        // Toggle button
        document.getElementById('toggleTerminalBtn')?.addEventListener('click', () => {
            this.toggle();
        });

        // Handle resize
        window.addEventListener('resize', () => {
            this.fit(this.activeTerminalId);
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 'j') {
                e.preventDefault();
                this.toggle();
            }
            if (e.ctrlKey && e.shiftKey && e.key === '`') {
                e.preventDefault();
                this.createNewTerminal();
            }
        });
    }

    /**
     * Clear active terminal
     */
    clear() {
        const data = this.terminals.get(this.activeTerminalId);
        if (data) {
            data.terminal.clear();
        }
    }

    /**
     * Write an error message to the active terminal
     */
    writeError(message) {
        const data = this.terminals.get(this.activeTerminalId);
        if (data && data.terminal) {
            data.terminal.writeln(`\r\n\x1b[1;31mError: ${message}\x1b[0m`);
        }
    }

    /**
     * Write a message to a specific or active terminal
     */
    write(message, terminalId = null) {
        const id = terminalId || this.activeTerminalId;
        const data = this.terminals.get(id);
        if (data && data.terminal) {
            data.terminal.write(message);
        }
    }
}

// Create global instance
window.terminalManager = new TerminalManager();
