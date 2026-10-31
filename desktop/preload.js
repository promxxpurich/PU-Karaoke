// ตัวเชื่อมหน้าเว็บกับโปรเซสหลัก: ให้เรียกได้แค่คำสั่งที่ main.js อนุญาต
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('kara', {
  get: () => ipcRenderer.invoke('state:get'),
  do: (action, arg) => ipcRenderer.invoke('state:do', action, arg),
  on: (fn) => ipcRenderer.on('state', (_e, s) => fn(s)),
});
