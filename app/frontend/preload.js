/**
 * preload.js - Electron Preload Script
 * 
 * Bridge between main process and renderer process
 */

const { contextBridge, ipcRenderer } = require('electron');

// Expose protected methods that allow the renderer process to use
// ipcRenderer without exposing the entire object
contextBridge.exposeInMainWorld('electronAPI', {
  // Add API methods here as needed
  navigateTo: (page) => {
    window.location.href = page;
  },
  windowControl: (action) => {
    ipcRenderer.send('window-control', action);
  },
  beginWindowResize: (edge, screenX, screenY, minWidth, minHeight) => {
    ipcRenderer.send('window-resize-start', { edge, screenX, screenY, minWidth, minHeight });
  },
  moveWindowResize: (screenX, screenY, minWidth, minHeight) => {
    ipcRenderer.send('window-resize-move', { screenX, screenY, minWidth, minHeight });
  },
  endWindowResize: () => {
    ipcRenderer.send('window-resize-end');
  },
});
