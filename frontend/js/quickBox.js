/**
 * AI Code Editor - Quick Box Module
 * Handles Command Palette (Ctrl+K) and Quick File Search (Ctrl+P)
 */

class QuickBoxManager {
    constructor() {
        this.isOpen = false;
        this.mode = 'files'; // 'files' or 'commands'
        this.results = [];
        this.selectedIndex = 0;
        this.allFiles = [];
        this.commands = [
            { id: 'save', title: 'Save File', subtitle: 'Save current active file', icon: 'save', action: () => window.editorManager?.saveFile() },
            { id: 'run', title: 'Run Code', subtitle: 'Execute current file', icon: 'play', action: () => window.App?.runCurrentFile() },
            { id: 'theme', title: 'Toggle Theme', subtitle: 'Switch between light and dark mode', icon: 'moon', action: () => window.App?.toggleTheme() },
            { id: 'new-file', title: 'New File', subtitle: 'Create a new file in workspace', icon: 'file-plus', action: () => window.fileTreeManager?.createNewFile() },
            { id: 'new-folder', title: 'New Folder', subtitle: 'Create a new folder in workspace', icon: 'folder-plus', action: () => window.fileTreeManager?.createNewFolder() },
            { id: 'open-folder', title: 'Open Folder', subtitle: 'Switch to a different project', icon: 'folder-search', action: () => window.fileTreeManager?.showOpenFolderModal() },
            { id: 'new-terminal', title: 'New Terminal', subtitle: 'Create a new terminal session', icon: 'plus', action: () => window.terminalManager?.createNewTerminal() },
            { id: 'clear-chat', title: 'Clear Chat', subtitle: 'Remove all AI assistant messages', icon: 'trash-2', action: () => window.agentManager?.clearChat() },
        ];
    }

    /**
     * Initialize the Quick Box
     */
    init() {
        this.setupEventListeners();
    }

    /**
     * Show the Quick Box in a specific mode
     */
    show(mode = 'files') {
        this.mode = mode;
        this.isOpen = true;
        this.selectedIndex = 0;

        const overlay = document.getElementById('quickBoxOverlay');
        const input = document.getElementById('quickBoxInput');
        const icon = document.getElementById('quickBoxIcon');

        if (!overlay || !input || !icon) return;

        // Reset input
        input.value = '';
        input.placeholder = mode === 'files' ? 'Search files...' : 'Search commands...';

        // Update icon
        icon.setAttribute('data-lucide', mode === 'files' ? 'search' : 'command');
        if (window.lucide) lucide.createIcons();

        // Refresh file list if in file mode
        if (mode === 'files') {
            this.refreshFileList();
        }

        // Show UI
        overlay.style.display = 'flex';
        input.focus();

        // Initial search to show all/recent
        this.search('');
    }

    /**
     * Hide the Quick Box
     */
    hide() {
        this.isOpen = false;
        const overlay = document.getElementById('quickBoxOverlay');
        if (overlay) overlay.style.display = 'none';
    }

    /**
     * Refresh the list of all files in workspace
     */
    refreshFileList() {
        if (!window.fileTreeManager) return;

        const files = [];
        const excludePatterns = ['.venv', 'venv', 'node_modules', '.git', '__pycache__', '.pytest_cache', 'dist', 'build', '.egg-info'];

        const shouldExclude = (path) => {
            return excludePatterns.some(pattern => path.includes(`/${pattern}/`) || path.includes(`\\${pattern}\\`));
        };

        const traverse = (items) => {
            items.forEach(item => {
                if (item.type === 'file' && !shouldExclude(item.path)) {
                    files.push({
                        path: item.path,
                        name: item.name,
                        icon: getFileIcon(item.name)
                    });
                }
                if (item.children && !shouldExclude(item.path)) {
                    traverse(item.children);
                }
            });
        };

        traverse(window.fileTreeManager.fileTree);
        this.allFiles = files;
    }

    /**
     * Perform search based on current mode
     */
    search(query) {
        query = query.toLowerCase().trim();

        if (this.mode === 'files') {
            this.results = this.searchFiles(query);
        } else {
            this.results = this.searchCommands(query);
        }

        this.selectedIndex = 0;
        this.renderResults();
    }

    /**
     * Simple fuzzy search for files
     */
    searchFiles(query) {
        if (!query) return this.allFiles.slice(0, 10); // Show first 10 when empty

        return this.allFiles
            .filter(f => f.path.toLowerCase().includes(query))
            .sort((a, b) => {
                // Prioritize exact filename matches over path matches
                const aNameMatch = a.name.toLowerCase().includes(query);
                const bNameMatch = b.name.toLowerCase().includes(query);
                if (aNameMatch && !bNameMatch) return -1;
                if (!aNameMatch && bNameMatch) return 1;
                return a.path.length - b.path.length;
            })
            .slice(0, 10);
    }

    /**
     * Search commands
     */
    searchCommands(query) {
        if (!query) return this.commands;

        return this.commands.filter(c =>
            c.title.toLowerCase().includes(query) ||
            c.subtitle.toLowerCase().includes(query)
        );
    }

    /**
     * Render search results
     */
    renderResults() {
        const container = document.getElementById('quickBoxResults');
        if (!container) return;

        if (this.results.length === 0) {
            container.innerHTML = `
                <div class="quick-result-item no-results">
                    <div class="quick-result-info">
                        <span class="quick-result-title">No matches found</span>
                    </div>
                </div>
            `;
            return;
        }

        container.innerHTML = this.results.map((result, index) => {
            const isSelected = index === this.selectedIndex;
            const title = this.mode === 'files' ? result.name : result.title;
            const subtitle = this.mode === 'files' ? result.path : result.subtitle;
            const icon = result.icon || 'file';

            return `
                <div class="quick-result-item ${isSelected ? 'selected' : ''}" data-index="${index}">
                    <div class="quick-result-icon">
                        <i data-lucide="${icon}"></i>
                    </div>
                    <div class="quick-result-info">
                        <span class="quick-result-title">${title}</span>
                        <span class="quick-result-subtitle">${subtitle}</span>
                    </div>
                </div>
            `;
        }).join('');

        if (window.lucide) lucide.createIcons();

        // Scroll selected into view
        const selected = container.querySelector('.selected');
        if (selected) {
            selected.scrollIntoView({ block: 'nearest' });
        }

        // Click handlers
        container.querySelectorAll('.quick-result-item').forEach(item => {
            item.addEventListener('click', () => {
                this.selectedIndex = parseInt(item.dataset.index);
                this.executeSelected();
            });
        });
    }

    /**
     * Execute the selected result
     */
    executeSelected() {
        const result = this.results[this.selectedIndex];
        if (!result) return;

        this.hide();

        if (this.mode === 'files') {
            window.fileTreeManager?.openFile(result.path);
        } else if (result.action) {
            result.action();
        }
    }

    /**
     * Setup event listeners
     */
    setupEventListeners() {
        const input = document.getElementById('quickBoxInput');
        const overlay = document.getElementById('quickBoxOverlay');

        // Global shortcuts
        document.addEventListener('keydown', (e) => {
            // Ctrl+P - Quick File Search
            if (e.ctrlKey && e.key === 'p') {
                e.preventDefault();
                this.show('files');
            }
            // Ctrl+K - Command Palette
            if (e.ctrlKey && e.key === 'k') {
                e.preventDefault();
                this.show('commands');
            }
            // ESC - Close
            if (e.key === 'Escape' && this.isOpen) {
                this.hide();
            }
        });

        // Overlay click to close
        overlay?.addEventListener('click', (e) => {
            if (e.target === overlay) this.hide();
        });

        // Input handling
        input?.addEventListener('input', (e) => {
            this.search(e.target.value);
        });

        input?.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                this.selectedIndex = (this.selectedIndex + 1) % this.results.length;
                this.renderResults();
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                this.selectedIndex = (this.selectedIndex - 1 + this.results.length) % this.results.length;
                this.renderResults();
            } else if (e.key === 'Enter') {
                e.preventDefault();
                this.executeSelected();
            }
        });
    }
}

// Create global instance
window.quickBoxManager = new QuickBoxManager();
