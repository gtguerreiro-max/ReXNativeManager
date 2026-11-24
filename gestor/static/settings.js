// A game's settings as the settings HUD in the game has them (F1, or Back + Start on a pad:
// ReXNative's renderer/src/hud/hud.cpp), for the PC game page's Settings and a game's Settings on
// the Deck page. Each row is one HUD setting: its choices are the values it writes in the game's
// settings file ([rexnative], [ui], [log]); `def` is the renderer's own default (its REXCVAR),
// what a file without the keys gets. `where`: both, the PC only (window, resolution, DLSS) or the
// Deck. Loaded by index.html and deck.html, before app.js and deck.js.
const SETTINGS_GROUPS = ['Display', 'Picture', 'Upscaler', 'DLSS 5', 'Developer'];
const GAME_SETTINGS = [
  { id: 'renderer', group: 'Display', label: 'Renderer', where: 'both', def: { 'rexnative.classic': false },
    choices: [['Native (ReXNative)', { 'rexnative.classic': false }], ['Classic (Xenia)', { 'rexnative.classic': true }]],
    hint: 'Native: ReXNative, with the settings below. Classic: Xenia\'s renderer, for a game the native one does not draw right yet.' },
  { id: 'screen', group: 'Display', label: 'Screen', where: 'both', def: { 'rexnative.display_monitor': false },
    choices: [['TV (console)', { 'rexnative.display_monitor': false }], ['PC monitor', { 'rexnative.display_monitor': true }]],
    hint: 'TV: the picture as the console sends it to an HDTV, a little dark on a monitor or the Steam Deck. PC monitor: lighter in the shadows.' },
  { id: 'frame_rate', group: 'Display', label: 'Frame rate', where: 'both', def: { 'rexnative.present_interval': 1 },
    choices: [['Every refresh (60 fps)', { 'rexnative.present_interval': 1 }], ['Every 2nd refresh (30 fps)', { 'rexnative.present_interval': 2 }]],
    hint: 'How often a frame is shown. Whether the game itself runs faster depends on the game.' },
  { id: 'menu_fps', group: 'Display', label: 'FPS limit', where: 'both', def: { 'rexnative.menu_fps': 60 },
    choices: [['30', { 'rexnative.menu_fps': 30 }], ['60', { 'rexnative.menu_fps': 60 }], ['Unlimited', { 'rexnative.menu_fps': 0 }]],
    hint: '60 keeps menus made for a console\'s 60 Hz at their speed on a faster display; 30 for a game the console ran at 30.' },
  { id: 'frame_latency', group: 'Display', label: 'Frame latency', where: 'both',
    def: { 'rexnative.frame_latency': 3, 'rexnative.frame_latency_auto': true },
    choices: [['Auto (1-2)', { 'rexnative.frame_latency': 1, 'rexnative.frame_latency_auto': true }],
              ['1', { 'rexnative.frame_latency': 1, 'rexnative.frame_latency_auto': false }],
              ['2', { 'rexnative.frame_latency': 2, 'rexnative.frame_latency_auto': false }],
              ['3', { 'rexnative.frame_latency': 3, 'rexnative.frame_latency_auto': false }]],
    // As the HUD reads it: 1 with auto is Auto; otherwise the number, whatever auto says.
    read: e => { const n = Number(e['rexnative.frame_latency']); return n <= 1 && String(e['rexnative.frame_latency_auto']) === 'true' ? 0 : Math.min(3, Math.max(1, n)); },
    hint: 'Frames the game may run ahead of the screen: 1 responds soonest, 3 is the steadiest when the GPU is near its limit. Auto: 1, and 2 while frames would miss the screen at 1.' },
  { id: 'window_mode', group: 'Display', label: 'Window', where: 'pc', def: { 'ui.fullscreen': false, 'ui.fullscreen_exclusive': false },
    choices: [['Windowed', { 'ui.fullscreen': false }], ['Full screen', { 'ui.fullscreen': true, 'ui.fullscreen_exclusive': false }],
              ['Full screen (exclusive)', { 'ui.fullscreen': true, 'ui.fullscreen_exclusive': true }]],
    hint: 'Full screen is a borderless window over the whole display; exclusive takes the display for the game alone.' },
  { id: 'window_size', group: 'Display', label: 'Window size', where: 'pc', def: { 'ui.window_width': 1280, 'ui.window_height': 720 },
    choices: [['1280x720', { 'ui.window_width': 1280, 'ui.window_height': 720 }], ['1600x900', { 'ui.window_width': 1600, 'ui.window_height': 900 }],
              ['1920x1080', { 'ui.window_width': 1920, 'ui.window_height': 1080 }], ['2560x1440', { 'ui.window_width': 2560, 'ui.window_height': 1440 }]],
    hint: 'The window\'s size on the desktop, when the game is not full screen.' },
  { id: 'resolution', group: 'Picture', label: 'Resolution', where: 'pc', def: { 'rexnative.resolution_scale': 1 },
    choices: [['1x (the game\'s)', { 'rexnative.resolution_scale': 1 }], ['2x', { 'rexnative.resolution_scale': 2 }], ['3x', { 'rexnative.resolution_scale': 3 }]],
    // On the Deck only when the game has 2x or 3x from the PC's settings, to take it back.
    deckIf: e => Number(e['rexnative.resolution_scale']) > 1,
    hint: 'The game drawn at 2x or 3x its resolution, as the Xbox One X and Series do: sharper, heavier on the GPU. After a restart. On the Steam Deck: 1x.' },
  { id: 'antialiasing', group: 'Picture', label: 'Antialiasing', where: 'both', def: { 'rexnative.upscaler': false, 'rexnative.msaa': 2 },
    choices: [['Off', { 'rexnative.upscaler': false, 'rexnative.msaa': 1 }], ['MSAA 2x (console)', { 'rexnative.upscaler': false, 'rexnative.msaa': 2 }],
              ['MSAA 4x', { 'rexnative.upscaler': false, 'rexnative.msaa': 4 }], ['MSAA 8x', { 'rexnative.upscaler': false, 'rexnative.msaa': 8 }],
              ['Upscaler (DLSS / FSR)', { 'rexnative.upscaler': true }]],
    read: e => { if (String(e['rexnative.upscaler']) === 'true') return 4; const m = Number(e['rexnative.msaa']); return { 1: 0, 4: 2, 8: 3 }[m] ?? 1; },
    hint: 'The 3D scene\'s multisampling (most games draw 2x on the console), or the upscaler\'s temporal anti-aliasing (its options under Upscaler).' },
  // The PC's only: on the Deck's 1280x800 screen a 720p game is shown at its own size, and FSR 1
  // never runs there (ReXNative's HUD hides them on the Deck too).
  // Under Antialiasing, which it acts on (the in-game menu has it there too).
  { id: 'battery_saver', group: 'Picture', label: 'Battery saver', where: 'both', def: { 'rexnative.battery_saver': false },
    choices: [['Off', { 'rexnative.battery_saver': false }], ['On', { 'rexnative.battery_saver': true }]],
    hint: 'On the battery, the upscaler off and the console\'s anti-aliasing (MSAA) in its place: about a third less power on the Steam Deck (Overlord II: 4.7 W against 6.2). Back on the charger, the upscaler again. On the Deck by default; games built from 2026-11-24.' },
  { id: 'scaling', group: 'Picture', label: 'Screen scaling', where: 'pc', def: { 'rexnative.fsr': true },
    choices: [['Bilinear', { 'rexnative.fsr': false }], ['AMD FSR 1', { 'rexnative.fsr': true }]],
    hint: 'The last step: the finished picture (the game\'s resolution, its HUD on it) scaled up to a larger window. FSR 1 keeps edges sharp, bilinear is softer. FSR 4 and DLSS work earlier, on the 3D scene; for them up to the screen\'s size, use Resolution 2x or 3x.' },
  { id: 'sharpening', group: 'Picture', label: 'FSR sharpening', where: 'pc', def: { 'rexnative.fsr_sharpness': 0.2 },
    choices: [['Soft', { 'rexnative.fsr_sharpness': 1 }], ['Medium', { 'rexnative.fsr_sharpness': 0.5 }], ['Sharp', { 'rexnative.fsr_sharpness': 0.2 }], ['Sharpest', { 'rexnative.fsr_sharpness': 0 }]],
    hint: 'How much FSR 1 sharpens the picture it scales up to the window.' },
  { id: 'anisotropy', group: 'Picture', label: 'Texture filtering', where: 'both', def: { 'rexnative.anisotropy': 16 },
    choices: [['Game\'s', { 'rexnative.anisotropy': 1 }], ['2x', { 'rexnative.anisotropy': 2 }], ['4x', { 'rexnative.anisotropy': 4 }], ['8x', { 'rexnative.anisotropy': 8 }], ['16x', { 'rexnative.anisotropy': 16 }]],
    hint: 'Anisotropic filtering: sharper ground seen at grazing angles. At the next start.' },
  { id: 'upscaler_backend', group: 'Upscaler', label: 'Upscaler type', where: 'pc', def: { 'rexnative.upscaler_backend': 'auto' },
    choices: [['Automatic', { 'rexnative.upscaler_backend': 'auto' }], ['NVIDIA DLSS', { 'rexnative.upscaler_backend': 'dlss' }], ['AMD FSR', { 'rexnative.upscaler_backend': 'fsr' }]],
    deckIf: e => e['rexnative.upscaler_backend'] === 'dlss',
    hint: 'Automatic: DLSS on an NVIDIA RTX GPU, FSR on the others. FSR runs on every GPU (the Steam Deck: Automatic).' },
  { id: 'fsr_version', group: 'Upscaler', label: 'FSR version', where: 'both', def: { 'rexnative.fsr_version': 'auto' },
    choices: [['Newest', { 'rexnative.fsr_version': 'auto' }], ['FSR 4', { 'rexnative.fsr_version': '4' }], ['FSR 3.1', { 'rexnative.fsr_version': '3' }]],
    hint: 'FSR 4 (AI, sharper) needs an AMD GPU and AMD\'s driver library (on the Steam Deck, GE-Proton fetches it); FSR 3.1 is lighter and runs everywhere.' },
  { id: 'upscaler_mode', group: 'Upscaler', label: 'Mode', where: 'both', def: { 'rexnative.upscaler_mode': 'native' },
    choices: [['Native AA', { 'rexnative.upscaler_mode': 'native' }], ['Quality', { 'rexnative.upscaler_mode': 'quality' }],
              ['Balanced', { 'rexnative.upscaler_mode': 'balanced' }], ['Performance', { 'rexnative.upscaler_mode': 'performance' }],
              ['Ultra performance', { 'rexnative.upscaler_mode': 'ultra' }]],
    read: e => { const m = String(e['rexnative.upscaler_mode'] || 'native'); return Math.max(0, ['native', 'quality', 'balanced', 'performance', 'ultra'].indexOf(m === 'dlaa' ? 'native' : m)); },
    hint: 'Native AA keeps the game\'s resolution and only anti-aliases; the others render smaller (faster) and rebuild the picture.' },
  { id: 'frame_generation', group: 'Upscaler', label: 'Frame generation (FSR)', where: 'both', def: { 'rexnative.frame_generation': false },
    choices: [['Off', { 'rexnative.frame_generation': false }], ['On', { 'rexnative.frame_generation': true }]],
    hint: 'A generated frame before each of the game\'s: twice the frames shown, the game at half the screen\'s rate (30 for 60 on the Steam Deck). Needs the upscaler.' },
  { id: 'dlss5', group: 'DLSS 5', label: 'DLSS 5 neural rendering', where: 'pc', def: { 'rexnative.dlss5': false },
    choices: [['Off', { 'rexnative.dlss5': false }], ['On', { 'rexnative.dlss5': true }]],
    deckIf: e => String(e['rexnative.dlss5']) === 'true',
    hint: 'NVIDIA DLSS 5 on the scene (an RTX GPU), with the upscaler on. Off on the Steam Deck.' },
  { id: 'dlss5_look', group: 'DLSS 5', label: 'DLSS 5 look', where: 'pc', def: { 'rexnative.dlss5_look': 'cinematic' },
    choices: [['Cinematic', { 'rexnative.dlss5_look': 'cinematic' }], ['Cinematic, 2 passes', { 'rexnative.dlss5_look': 'cinematic2' }],
              ['Natural', { 'rexnative.dlss5_look': 'natural' }], ['Stylized', { 'rexnative.dlss5_look': 'stylized' }],
              ['Cel-shaded / 2D', { 'rexnative.dlss5_look': 'cel' }], ['Strong', { 'rexnative.dlss5_look': 'strong' }]],
    hint: 'Cinematic: realistic games. 2 passes: racing, heavier. Natural: nearer the game\'s colours. Stylized: cartoon or painterly 3D. Cel-shaded / 2D: flat colours kept.' },
  { id: 'dlss5_intensity', group: 'DLSS 5', label: 'DLSS 5 intensity', where: 'pc', def: { 'rexnative.dlss5_intensity': 1 },
    choices: [['Low', { 'rexnative.dlss5_intensity': 0.5 }], ['Medium', { 'rexnative.dlss5_intensity': 0.75 }], ['Full', { 'rexnative.dlss5_intensity': 1 }], ['Strong', { 'rexnative.dlss5_intensity': 1.25 }]],
    hint: 'How strongly DLSS 5 changes the picture, on top of the look\'s own.' },
  { id: 'dlss5_reuse', group: 'DLSS 5', label: 'DLSS 5 speed', where: 'pc', def: { 'rexnative.dlss5_reuse': 0 },
    choices: [['Every frame', { 'rexnative.dlss5_reuse': 0 }], ['Every 2nd frame', { 'rexnative.dlss5_reuse': 1 }], ['Every 3rd frame', { 'rexnative.dlss5_reuse': 2 }]],
    hint: 'How often DLSS 5 runs: every 2nd frame nearly halves its cost (best for slower games).' },
  { id: 'dlss5_hold', group: 'DLSS 5', label: 'DLSS 5 still hold', where: 'pc', def: { 'rexnative.dlss5_hold': 0 },
    choices: [['Off', { 'rexnative.dlss5_hold': 0 }], ['Gentle', { 'rexnative.dlss5_hold': 0.8 }], ['Strong', { 'rexnative.dlss5_hold': 0.95 }]],
    hint: 'Where the picture stands still, DLSS 5\'s last answer is kept: no slow drift when the camera stops.' },
  { id: 'dlss5_mv_check', group: 'DLSS 5', label: 'DLSS 5 motion check', where: 'pc', def: { 'rexnative.dlss5_mv_check': false },
    choices: [['Off', { 'rexnative.dlss5_mv_check': false }], ['On', { 'rexnative.dlss5_mv_check': true }]],
    hint: 'Checks the scene\'s motion before DLSS 5 gets it: no smear where a vector is wrong.' },
  { id: 'occlusion', group: 'Developer', label: 'Occlusion queries', where: 'both', def: {},
    choices: [['Off', { 'rexnative.occlusion': false }], ['On', { 'rexnative.occlusion': true }]],
    hint: 'The game\'s visibility tests counted on the GPU. Off: everything drawn. The default is the game\'s own.' },
  { id: 'log_level', group: 'Developer', label: 'Log level', where: 'both', def: {},
    choices: [['Errors', { 'log.level': 'error' }], ['Warnings', { 'log.level': 'warn' }], ['Info', { 'log.level': 'info' }], ['Debug', { 'log.level': 'debug' }]],
    hint: 'How much the game writes to its log: Info normally, Debug for a bug report.' },
];

// The rows for the PC's file ('pc') or the Deck's ('deck'): on the Deck, a PC's row too where the
// game has a PC's value there (deckIf; every one of them when eff is not given).
function settingsFor(target, eff) {
  return GAME_SETTINGS.filter(s => s.where === 'both' || s.where === target ||
    (target === 'deck' && s.deckIf && (!eff || s.deckIf(Object.assign({}, s.def, eff)))));
}
// Every key a row writes.
function settingKeys(s) {
  const keys = new Set(Object.keys(s.def));
  for (const [, set] of s.choices) Object.keys(set).forEach(k => keys.add(k));
  return [...keys];
}
function sameValue(a, b) {
  if (a === undefined || b === undefined) return false;
  const sa = String(a), sb = String(b);
  if (sa === sb) return true;
  const num = /^-?\d+(\.\d+)?$/;
  return num.test(sa) && num.test(sb) && Number(sa) === Number(sb);  // 1 and 1.0
}
// The choice a row shows for these values (the file's over the defaults' over the renderer's),
// -1 when none of its choices is what they say (or the renderer's default is the game's own).
function settingIndex(s, eff) {
  const e = Object.assign({}, s.def, eff);
  if (settingKeys(s).every(k => e[k] === undefined)) return -1;
  if (s.read) return s.read(e);
  return s.choices.findIndex(([, set]) => Object.entries(set).every(([k, v]) => sameValue(e[k], v)));
}
// Whether the file sets any of the row's keys itself.
function settingSet(s, vals) {
  return settingKeys(s).some(k => vals[k] !== undefined);
}
