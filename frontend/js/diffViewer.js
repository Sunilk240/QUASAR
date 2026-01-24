/**
 * QUASAR - Code Diff Viewer
 * Handles visual diffing for AI-suggested changes
 */

class DiffViewer {
    constructor() {
        this.dmp = new diff_match_patch();
    }

    /**
     * Generate HTML for a unified diff
     * @param {string} oldText - Original code
     * @param {string} newText - Modified code
     * @param {string} fileName - Name of the file being diffed
     * @returns {string} HTML string representing the diff
     */
    renderDiff(oldText, newText, fileName = '') {
        if (!oldText && !newText) return '<div class="diff-empty">No changes to show</div>';

        // Diff-match-patch doesn't do line-by-line diff naturally, 
        // but we can use their diff_main and then clean it up for lines.
        const diffs = this.dmp.diff_main(oldText || '', newText || '');
        this.dmp.diff_cleanupSemantic(diffs);

        let html = `
            <div class="diff-viewer">
                ${fileName ? `<div class="diff-filename">${fileName}</div>` : ''}
                <div class="diff-content">
        `;

        // Process diffs into line blocks
        // 0 = equal, -1 = delete, 1 = insert
        diffs.forEach(part => {
            const type = part[0];
            const text = part[1];
            const escaped = this.escapeHtml(text);

            if (type === 0) {
                html += `<span class="diff-equal">${escaped}</span>`;
            } else if (type === -1) {
                html += `<span class="diff-delete">${escaped}</span>`;
            } else if (type === 1) {
                html += `<span class="diff-insert">${escaped}</span>`;
            }
        });

        html += `
                </div>
            </div>
        `;

        return html;
    }

    /**
     * Line-by-line unified diff (More professional for code)
     */
    renderLineDiff(oldText, newText, fileName = '') {
        const oldLines = (oldText || '').split('\n');
        const newLines = (newText || '').split('\n');

        // Simple line diff logic
        // For a really robust line diff, we'd use LCS, but let's try a simpler approach 
        // or just use DMP if we can hack it to be line-based.

        // DMP line-based approach:
        const a = this.dmp.diff_linesToChars_(oldText || '', newText || '');
        const lineText1 = a.chars1;
        const lineText2 = a.chars2;
        const lineArray = a.lineArray;

        const diffs = this.dmp.diff_main(lineText1, lineText2, false);
        this.dmp.diff_charsToLines_(diffs, lineArray);
        this.dmp.diff_cleanupSemantic(diffs);

        let html = `
            <div class="diff-container">
                <div class="diff-header">
                    <span class="diff-title">Suggested Changes</span>
                    ${fileName ? `<span class="diff-file-tag">${fileName}</span>` : ''}
                </div>
                <div class="diff-lines">
        `;

        diffs.forEach(part => {
            const type = part[0]; // 0: equal, -1: delete, 1: insert
            const text = part[1];
            const lines = text.split('\n');

            // Remove trailing empty line from split
            if (lines[lines.length - 1] === '') lines.pop();

            lines.forEach(line => {
                let cls = '';
                let prefix = ' ';
                if (type === -1) { cls = 'diff-line-delete'; prefix = '-'; }
                else if (type === 1) { cls = 'diff-line-insert'; prefix = '+'; }
                else { cls = 'diff-line-equal'; prefix = ' '; }

                html += `<div class="diff-line ${cls}"><span class="diff-prefix">${prefix}</span><span class="diff-text">${this.escapeHtml(line)}</span></div>`;
            });
        });

        html += `
                </div>
            </div>
        `;

        return html;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Global instance
window.diffViewer = new DiffViewer();
