/**
 * AI Code Editor - Main Application
 * Entry point that initializes all modules
 */

class App {
    constructor() {
        this.initialized = false;
    }

    /**
     * Initialize the application
     */
    async init() {
        console.log('🚀 Initializing AI Code Editor...');

        try {
            // Show loading state
            this.showLoading(true);

            // Initialize Monaco Editor first (async)
            console.log('📝 Loading Monaco Editor...');
            await window.editorManager.init();
            console.log('✅ Monaco Editor ready');

            // Initialize Settings after Monaco so they can be applied
            console.log('⚙️ Initializing Settings...');
            window.settingsManager.init();

            // Initialize Terminal
            console.log('🖥️ Initializing Terminal...');
            window.terminalManager.init();
            console.log('✅ Terminal ready');

            // Initialize File Tree
            console.log('📁 Initializing File Tree...');
            window.fileTreeManager.init();
            console.log('✅ File Tree ready');

            // Initialize Agent
            console.log('🤖 Initializing AI Agent...');
            window.agentManager.init();
            console.log('✅ AI Agent ready');

            // Initialize Resizers
            console.log('↔️ Initializing Resizers...');
            window.resizerManager.init();
            console.log('✅ Resizers ready');

            // Initialize Quick Box
            console.log('🔍 Initializing Quick Box...');
            window.quickBoxManager.init();
            console.log('✅ Quick Box ready');

            // Setup global event listeners
            this.setupEventListeners();

            // Initialize Lucide icons
            if (window.lucide) {
                lucide.createIcons();
            }

            // Mark as initialized
            this.initialized = true;
            this.showLoading(false);

            console.log('✅ AI Code Editor initialized successfully!');

            // Update status bar
            this.updateConnectionStatus('connected');

        } catch (error) {
            console.error('❌ Failed to initialize:', error);
            this.showError('Failed to initialize the editor. Please refresh the page.');
        }
    }

    /**
     * Setup global event listeners
     */
    setupEventListeners() {
        // Save button
        document.getElementById('saveBtn')?.addEventListener('click', async () => {
            await this.saveCurrentFile();
        });

        // Run button
        document.getElementById('runBtn')?.addEventListener('click', () => {
            this.runCurrentFile();
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // Prevent browser defaults for our shortcuts (Save, Run, Command Palette, Search, File Tree, Terminal, Agent)
            if (e.ctrlKey && ['s', 'r', 'k', 'p', 'b', 'j', '/'].includes(e.key)) {
                e.preventDefault();
            }
        });

        // Handle page unload with unsaved changes
        window.addEventListener('beforeunload', (e) => {
            if (this.hasUnsavedChanges()) {
                e.preventDefault();
                e.returnValue = 'You have unsaved changes. Are you sure you want to leave?';
            }
        });

        // Handle window resize
        window.addEventListener('resize', () => {
            window.editorManager?.layout();
            window.terminalManager?.fit();
        });
    }

    /**
     * Save current file
     */
    async saveCurrentFile() {
        const fileData = await window.editorManager?.saveFile();

        if (fileData) {
            console.log('Saving file:', fileData.path);
            window.terminalManager?.writeSuccess(`✓ Saved: ${fileData.path}`);
        } else {
            window.terminalManager?.writeWarning('⚠ No file to save');
            window.toast?.warning('No file to save');
        }
    }

    /**
     * Run current file (executes in the terminal like VS Code)
     */
    async runCurrentFile() {
        const editor = window.editorManager;
        const terminal = window.terminalManager;

        if (!editor?.getActiveFilePath()) {
            terminal?.writeWarning('⚠ No file open to run');
            return;
        }

        const filePath = editor.getActiveFilePath();
        const language = detectLanguage(filePath);

        // Check if language is supported
        if (!['python', 'javascript'].includes(language)) {
            terminal?.writeWarning(`⚠ Language "${language}" execution not supported yet.`);
            terminal?.writeInfo('Supported languages: Python (.py), JavaScript (.js)');
            return;
        }

        // Save file first before running
        await this.saveCurrentFile();

        // Build the run command based on language
        let command = '';
        if (language === 'python') {
            command = `python "${filePath}"`;
        } else if (language === 'javascript') {
            command = `node "${filePath}"`;
        }

        // Execute in the terminal (like VS Code)
        terminal?.runCommand(command);

        console.log('▶ Running:', command);
    }

    /**
     * Check for unsaved changes
     */
    hasUnsavedChanges() {
        // Check if any open file has unsaved changes
        return window.editorManager?.isDirty() || false;
    }

    /**
     * Update connection status in status bar
     */
    updateConnectionStatus(status) {
        const element = document.getElementById('statusConnection');
        const icon = element?.querySelector('[data-lucide]');
        const text = element?.querySelector('span:last-child');

        if (status === 'connected') {
            element?.classList.add('connected');
            element?.classList.remove('disconnected');
            if (icon) icon.setAttribute('data-lucide', 'wifi');
            if (text) text.textContent = 'Ready';
        } else {
            element?.classList.remove('connected');
            element?.classList.add('disconnected');
            if (icon) icon.setAttribute('data-lucide', 'wifi-off');
            if (text) text.textContent = 'Offline';
        }

        lucide?.createIcons();
    }

    /**
     * Show loading state
     */
    showLoading(show) {
        if (show) {
            document.body.style.cursor = 'wait';
        } else {
            document.body.style.cursor = '';
        }
    }

    /**
     * Show error message
     */
    showError(message) {
        console.error(message);
        window.terminalManager?.writeError(message);
        window.toast?.error(message);
    }
}

// Create and initialize app
const app = new App();
window.App = app; // Expose globally for Quick Box
document.addEventListener('DOMContentLoaded', () => app.init());
