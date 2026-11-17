"use strict";
// Iconos de trazo del panel (viewBox 24). Se usan con icono("nombre") o <i data-icono="nombre">.
const ICONOS = {
  rejilla: '<rect x="3" y="3" width="7" height="7" rx="1.3"/><rect x="14" y="3" width="7" height="7" rx="1.3"/><rect x="3" y="14" width="7" height="7" rx="1.3"/><rect x="14" y="14" width="7" height="7" rx="1.3"/>',
  capas: '<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5M3 16l9 5 9-5"/>',
  pelicula: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 3v18M17 3v18M3 8h4M3 16h4M17 8h4M17 16h4"/>',
  ajustes: '<path d="m9 3-1 3-3 1-2 3 2 2-1 3 2 3 3-1 2 2 4-1 1-3 3-1 1-4-2-2 1-3-3-2-3 1-2-1Z"/><circle cx="12" cy="11" r="3"/>',
  monitor: '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>',
  dispositivos: '<rect x="2" y="3" width="14" height="13" rx="2"/><path d="M6 20h6M9 16v4"/><rect x="17" y="9" width="5" height="12" rx="1"/>',
  panel: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/>',
  buscar: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/>',
  check: '<path d="m5 12 5 5 9-10"/>',
  mas:'<path d="M12 5v14M5 12h14"/>',
  "check-circulo": '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
  youtube: '<rect x="2.5" y="5" width="19" height="14" rx="4"/><path d="m10 9 5 3-5 3V9Z"/>',
  enlace: '<path d="m10 14 4-4m-5-2 2-2a4 4 0 0 1 6 6l-2 2m-6-4-2 2a4 4 0 0 0 6 6l2-2"/>',
  flecha: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
  subir: '<path d="M12 16V3m-5 5 5-5 5 5M4 15v5h16v-5"/>',
  cerrar: '<path d="m6 6 12 12M18 6 6 18"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  deslizadores: '<path d="M4 7h7m4 0h5M4 17h3m4 0h9"/><circle cx="13" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
  ojo: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
  salir: '<path d="M10 4H5v16h5M15 8l4 4-4 4M19 12H9"/>',
  papelera:'<path d="M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7M14 10v7"/>',
};
const icono = (nombre) => `<svg class="ic" viewBox="0 0 24 24" aria-hidden="true">${ICONOS[nombre] || ICONOS.pelicula}</svg>`;
