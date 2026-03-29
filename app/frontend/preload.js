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
  }
});
