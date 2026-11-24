// Mock Home Assistant `hass` for the MagicbHAnds page (regression stage "page").
// Made-up names and IDs only: this repository is public.
//
// Loaded by the harness's parent page before frontend/panel.js. Reads its knobs from window.__MOCK_OPTS and exposes:
//   window.__mock.hass     the hass object the panel is given (states, entities, devices, areas, callService, callWS, fetchWithAuth)
//   window.__calls         every call the page made: ['svc', domain, service, data] | ['ws', type, domain, service, data] | ['fetch', url, method]
//   window.__mockReject    a RegExp: matching calls ("domain.service", or the fetch method + url) reject with "MOCK-REJECT ..."
//
// Entity names follow the firmware (esphome/magicband-reader.yaml, magicband-bridge.yaml + magicband-addon.yaml,
// screek-bp2-poe.yaml) and the integration (custom_components/magicband/*.py).
(function () {
  const O = Object.assign({
    readerFirst: false,      // the readers' devices come before the integration's service device
    rgbw: false,             // the front reader has an RGBW ring (Ring type RGBW warm white, rgbw_color)
    oldFirmware: false,      // readers and bridges run old firmware: none of the newer entities exist
    autoUpdates: true,       // Automatic updates + Time zone exist on readers and bridges
    night: false,            // Night now is on for both readers
    lockedOut: true,         // the garage reader is locked out (Tap lockout on)
    lockdown: false,         // the house Lockdown is on (by hand)
    guestPass: 'active',     // Sam's guest pass: active | expired | none (not a guest)
    btOnly: true,            // an unlinked Bluetooth-only MagicBand+ (7F3C) exists
    unknown: 1,              // unknown bands waiting (0, 1 or 2)
    lowBattery: true,        // Casey's MagicBand+ is at 15 %
    unpaired: true,          // the garage reader isn't paired
    everyBand: false,        // the front reader's Response mode is Welcome every band
    listFailed: true,        // the garage reader turned the allowed list down
    updateAvailable: true,   // the garage reader has a firmware update
    garageOffline: false,    // every garage reader entity is unavailable
    bandTypesKnown: false,   // every NFC band has its type set (no "Which kind of band?")
    idleStyle: 'Circle',     // front reader Idle style (Circle = effect Idle circle; Static = effect None)
    idleStyleGarage: 'Static',
    idleStyleNightGarage: 'Same as day',
    soundAtNight: 'Quieter', // front reader
    soundAtNightGarage: 'Normal',
    idleHeads: 1, idleTail: 0, idleFade: 10, idleDir: 'Forward', idleTime: 3, ledCount: 24,
    bridgeProxy: true,       // the Kitchen Bridge has a Bluetooth proxy switch (the BP2 never has one)
    passport: true,          // the tap passport is on
    welcomeSound: true,      // Morgan has a welcome sound
    history: true,           // the history service answers (else it fails with historyError)
    historyError: 'Unauthorized',
    cameras: true,
    readerTz: 'Eastern (New York)',   // the readers' Time zone setting
    strangers: false,        // add a smart plug on another integration's device, and two dangerous reader buttons under harmless ids
  }, window.__MOCK_OPTS || {});
  if (O.clean) Object.assign(O, { lockedOut: false, unpaired: false, lowBattery: false, listFailed: false, unknown: 0, btOnly: false, bandTypesKnown: true }, O.clean === true ? {} : O.clean);

  const NOW = Date.now(), iso = ms => new Date(ms).toISOString(), min = m => iso(NOW - m * 60000);
  const states = {}, entities = {}, devices = {}, areas = {};
  [['front', 'Front porch'], ['garage', 'Garage'], ['kitchen', 'Kitchen'], ['office', 'Office']].forEach(([id, n]) => areas[id] = { area_id: id, name: n });
  function dev(id, name, model, area, extra) { devices[id] = Object.assign({ id, name, name_by_user: null, model, manufacturer: 'MagicbHAnds', area_id: area || null }, extra || {}); return devices[id]; }
  function ent(eid, state, attrs, devId, platform, cat, lu) {
    states[eid] = { entity_id: eid, state: String(state), attributes: attrs || {}, last_updated: lu || min(30), last_changed: lu || min(30) };
    entities[eid] = { entity_id: eid, device_id: devId, platform, entity_category: cat || null, hidden: false };
  }
  const slug = s => s.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
  // the firmware's newer entities: absent with oldFirmware
  const NEWER = new Set(['Idle circle time', 'Idle circle tail', 'Idle tail fade', 'Idle circle heads', 'Idle circle direction', 'Idle style', 'Idle style at night',
    'Sound at night', 'Night volume', 'Refused-tap lockout', 'Lockout after', 'Lockout window', 'Lockout time', 'Tap lockout', 'Band light-up power',
    'Paired with MagicbHAnds', 'Automatic updates', 'Time zone', 'Night now', 'Loop time', 'Largest free block']);
  const AUTO = new Set(['Automatic updates', 'Time zone']);
  const has = label => !(O.oldFirmware && NEWER.has(label)) && !(!O.autoUpdates && AUTO.has(label));
  const FW = O.oldFirmware ? '0.10.4' : O.autoUpdates ? '0.10.31' : '0.10.30';
  const TZ = ['Eastern (New York)', 'Central (Chicago)', 'Mountain (Denver)', 'Arizona (Phoenix)', 'Pacific (Los Angeles)', 'Alaska (Anchorage)', 'Hawaii (Honolulu)', 'UK (London)', 'Central Europe (Paris)', 'UTC'];

  // ---- readers (ESPHome magicband-reader) ----
  const COL = ['White', 'Warm white', 'Red', 'Orange', 'Yellow', 'Green', 'Cyan', 'Blue', 'Purple', 'Pink', 'Magenta'];
  const SHOWS = ['Rainbow rush', 'Fireworks', 'Comet chase', 'Colour parade', 'Twinkle', 'Heartbeat', 'Ocean', 'Fire', 'Pinwheel', 'Confetti', 'Penguins', 'Goal', 'Aurora', 'Candy cane', 'Thunderstorm', 'Sunrise', 'Disco', 'Birthday', 'New Year', 'Valentine', 'St Patrick', 'Easter', 'Stars and Stripes', 'Halloween', 'Thanksgiving', 'Hanukkah', 'Christmas', 'Stamp'];
  function reader(id, name, area, opt) {
    dev(id, name, 'magicband-reader', area, { manufacturer: 'legal-copy7045' }); const p = slug(name);
    const E = (dom, label, state, attrs, cat, plat) => { if (!has(label)) return; ent(`${dom}.${p}_${slug(label)}`, opt.offline && plat !== 'magicband' ? 'unavailable' : state, Object.assign({ friendly_name: `${name} ${label}` }, attrs || {}), id, plat || 'esphome', cat); };
    const ringAttrs = opt.rgbw ? { effect: opt.effect, rgbw_color: [0, 0, 0, 255], brightness: 255, supported_color_modes: ['rgbw'] } : { effect: opt.effect, rgb_color: [255, 255, 255], brightness: 77, supported_color_modes: ['rgb'] };
    E('light', 'Ring', 'on', ringAttrs, null);
    E('media_player', 'Speaker', 'idle', { volume_level: opt.vol });
    const sel = (l, s, o) => E('select', l, s, { options: o }, 'config');
    sel('Response mode', opt.every ? 'Welcome every band' : 'Known bands only', ['Known bands only', 'Welcome every band', 'Ask Home Assistant']);
    sel('Ring type', opt.rgbw ? 'RGBW warm white' : 'RGB', ['RGB', 'RGBW warm white', 'RGBW neutral white', 'RGBW cool white']);
    sel('LED colour order', 'GRB', ['GRB', 'RGB']);
    sel('Startup show', 'Rainbow rush', ['Off', 'Random', ...SHOWS]);
    sel('Show', 'Random', ['Random', ...SHOWS]);
    sel('Idle style', opt.style, ['Static', 'Circle']);
    sel('Idle style at night', opt.styleNight || 'Same as day', ['Same as day', 'Static', 'Circle']);
    sel('Idle colour', 'White', COL); sel('Idle circle direction', opt.dir || 'Forward', ['Forward', 'Reverse']);
    sel('Night mode', opt.sun ? 'Sunset to sunrise' : 'Set hours', ['Set hours', 'Sunset to sunrise']);
    sel('Sound at night', opt.soundNight, ['Normal', 'Quieter', 'Off']);
    sel('Checking colour', 'White', COL); sel('Welcome colour', 'Green', COL); sel('Denied colour', 'Red', COL);
    sel('Band light-up power', '-12 dBm', ['-24 dBm', '-21 dBm', '-18 dBm', '-15 dBm', '-12 dBm', '-9 dBm', '-6 dBm', '-3 dBm', '0 dBm']);
    sel('Time zone', O.readerTz, TZ);
    const num = (l, s, u, mn, mx, st) => E('number', l, s, { unit_of_measurement: u, min: mn, max: mx, step: st, mode: 'box' }, 'config');
    num('LED count', opt.leds || 24, undefined, 1, 60, 1); num('LED brightness', 100, '%', 5, 100, 5); num('Idle glow', 30, '%', 0, 100, 5);
    num('Idle circle time', opt.time || 3, 's', 0.5, 10, 0.5); num('Idle circle tail', opt.tail || 0, 'LEDs', 0, 60, 1); num('Idle tail fade', opt.fade != null ? opt.fade : 10, '%', 0, 100, 5); num('Idle circle heads', opt.heads || 1, undefined, 1, 4, 1);
    num('Idle glow at night', 10, '%', 0, 100, 5); num('Night volume', 30, '%', 5, 100, 5); num('Night from', 22, 'h', 0, 23, 1); num('Night until', 6, 'h', 0, 23, 1);
    num('Night starts after sunset', 0, 'min', -240, 240, 5); num('Night ends after sunrise', 30, 'min', -240, 240, 5);
    num('Checking circles', 2, undefined, 1, 5, 1); num('Circle time', 0.5, 's', 0.2, 2, 0.1); num('Circle tail', 0, 'LEDs', 0, 60, 1);
    num('Welcome fade in', 0.15, 's', 0, 2, 0.05); num('Welcome hold', 1, 's', 0, 10, 0.1); num('Welcome fade out', 1, 's', 0, 5, 0.05); num('Welcome pulses', 1, undefined, 1, 5, 1);
    num('Denied pulses', 2, undefined, 1, 5, 1); num('Pulse time', 0.45, 's', 0.2, 1.5, 0.05);
    num('Lockout after', 5, 'refusals', 2, 20, 1); num('Lockout window', 60, 's', 10, 600, 10); num('Lockout time', 5, 'min', 1, 60, 1);
    E('switch', 'Sound', 'on', {}, 'config'); E('switch', 'Light up MagicBand+', 'on', {}, 'config'); E('switch', 'Refused-tap lockout', opt.lockout ? 'on' : 'off', {}, 'config');
    E('switch', 'Automatic updates', 'off', {}, 'config');
    E('binary_sensor', 'Night now', O.night ? 'on' : 'off', {}, 'diagnostic'); E('binary_sensor', 'Tap lockout', opt.lockedNow ? 'on' : 'off', { device_class: 'problem' }, 'diagnostic');
    E('binary_sensor', 'Paired with MagicbHAnds', opt.paired ? 'on' : 'off', {}, 'diagnostic');
    ['Test welcome', 'Play show', 'Restart', 'Allow last band', 'Forget last band', 'Forget all bands'].forEach(b => E('button', b, 'unknown', {}, b === 'Restart' ? 'diagnostic' : null));
    E('sensor', 'Known bands', opt.known, {}, 'diagnostic');
    E('sensor', 'Wi-Fi signal', opt.wifi, { unit_of_measurement: 'dBm' }, 'diagnostic');
    E('sensor', 'CPU temperature', opt.cpu, { unit_of_measurement: '°C' }, 'diagnostic');
    E('sensor', 'Last restart', min(opt.upMin), { device_class: 'timestamp' }, 'diagnostic');
    E('sensor', 'Free memory', 84000, { unit_of_measurement: 'B' }, 'diagnostic'); E('sensor', 'Largest free block', 61000, { unit_of_measurement: 'B' }, 'diagnostic');
    E('sensor', 'Loop time', opt.loop, { unit_of_measurement: 'ms' }, 'diagnostic');
    E('sensor', 'Reset reason', opt.reset, {}, 'diagnostic'); E('sensor', 'IP address', opt.ip, {}, 'diagnostic'); E('sensor', 'Wi-Fi network', 'LakeviewNet', {}, 'diagnostic');
    E('sensor', 'Last band ID', opt.lastId, {}, 'diagnostic');
    E('update', 'Firmware', opt.update ? 'on' : 'off', { installed_version: FW, latest_version: opt.update ? '0.10.32' : FW }, 'config');
    // the integration's own entities on the reader device
    E('sensor', 'Last band name', opt.lastName, { band_id: opt.lastId, band: opt.lastId, person: opt.lastPerson, allowed: true, at: min(4) }, null, 'magicband');
    E('sensor', 'Allowed list', opt.list, { error: opt.listErr || null, last_sync: min(3), bands: opt.known, welcome_colours: true }, 'diagnostic', 'magicband');
  }
  function readers() {
    reader('dev_r1', 'Front Door Reader', 'front', { effect: O.idleStyle === 'Circle' ? 'Idle circle' : 'None', style: O.idleStyle, rgbw: O.rgbw, every: O.everyBand, vol: 0.6, sun: true, known: 5, wifi: -58, cpu: 51, upMin: 60 * 30, loop: 220, reset: 'Software reset', ip: '10.20.30.41', lastId: '04-1A-2B-3C-4D-5E-01', lastName: "Morgan's MagicBand+", lastPerson: 'Morgan', list: 'up_to_date', lockout: true, paired: true, soundNight: O.soundAtNight, heads: O.idleHeads, tail: O.idleTail, fade: O.idleFade, dir: O.idleDir, time: O.idleTime, leds: O.ledCount });
    reader('dev_r2', 'Garage Reader', 'garage', { effect: O.idleStyleGarage === 'Circle' ? 'Idle circle' : 'None', style: O.idleStyleGarage, styleNight: O.idleStyleNightGarage, vol: 0.4, sun: false, known: 4, wifi: -77, cpu: 68, upMin: 50, loop: 1400, reset: 'Brownout reset', ip: '10.20.30.42', lastId: '04-99-88-77-66-55-44', lastName: '04-99-88-77-66-55-44', lastPerson: null, list: O.garageOffline ? 'offline' : O.listFailed ? 'failed' : 'up_to_date', listErr: O.listFailed ? 'The list was too long for this reader' : null, update: O.updateAvailable, lockout: O.lockedOut, lockedNow: O.lockedOut, paired: !O.unpaired, soundNight: O.soundAtNightGarage, offline: O.garageOffline });
  }

  // ---- the integration's service device ----
  function service() {
    dev('dev_mb', 'MagicbHAnds', null, null, { entry_type: 'service' });
    const S = (eid, state, attrs, lu) => ent(eid, state, attrs, 'dev_mb', 'magicband', null, lu);
    S('sensor.magicband_last_tap', min(4), { friendly_name: 'MagicbHAnds Last tap', band: '04-1A-2B-3C-4D-5E-01', label: null, person: 'Morgan', ha_person: 'person.morgan', allowed: true, reader: 'Front Door Reader', device_class: 'timestamp' });
    const UNK = [{ band: '04-99-88-77-66-55-44', last_seen: min(26), reader: 'Garage Reader', scans: 3 }, { band: '04-77-66-55-44-33-22', last_seen: min(70), reader: 'Front Door Reader', scans: 1 }].slice(0, O.unknown);
    S('sensor.magicband_unknown_bands', UNK.length, { friendly_name: 'MagicbHAnds Unknown bands', unit_of_measurement: 'bands', bands: UNK, enrolling: null });
    S('sensor.magicband_last_band_heard', min(2), { friendly_name: 'MagicbHAnds Last band heard', listening: true });
    S('binary_sensor.magicbhands_lockdown', O.lockdown ? 'on' : 'off', { friendly_name: 'MagicbHAnds Lockdown', reasons: O.lockdown ? ['by hand'] : [] });
    const person = (n, ha, allowed, bands, last, reader) => S(`sensor.magicband_${slug(n)}_last_tap`, last ? min(last) : 'unknown', { friendly_name: `MagicbHAnds ${n} last tap`, ha_person: ha, allowed, bands, last_band: bands[0] ? bands[0].band : null, last_reader: reader, device_class: 'timestamp' });
    person('Morgan', 'person.morgan', true, [{ band: '04-1A-2B-3C-4D-5E-01', label: null }, { band: '04-1A-2B-3C-4D-5E-02', label: 'Blue' }], 4, 'Front Door Reader');
    person('Casey', 'person.casey', true, [{ band: '04-2B-3C-4D-5E-6F-03', label: null }, { band: '04-2B-3C-4D-5E-6F-04', label: 'Old band' }], 180, 'Garage Reader');
    person('Alex', null, false, [{ band: '04-3C-4D-5E-6F-70-05', label: null }], 60 * 30, 'Front Door Reader');
    person('Sam', null, true, [{ band: '04-4D-5E-6F-70-81-06', label: 'Dog walker' }], 60 * 24 * 2, 'Front Door Reader');
  }

  // ---- bands (the integration's band devices) ----
  function band(id, name, o) {
    dev(id, name, o.bt ? 'MagicBand+' : 'MagicBand', null);
    const p = slug(name), E = (dom, label, state, attrs, cat) => ent(`${dom}.${p}_${slug(label)}`, state, Object.assign({ friendly_name: `${name} ${label}` }, attrs || {}), id, 'magicband', cat);
    if (o.nfc) {
      E('sensor', 'Last tap', o.tap != null ? min(o.tap) : 'unknown', { device_class: 'timestamp', band: o.nfc, label: o.label || null, person: o.person, ha_person: null, allowed: o.allowed !== false, reader: o.reader || null, scans: o.scans || 0, first_seen: min(60 * 24 * 40), bluetooth_band: o.bt || null, band_type: o.type });
      E('select', 'Band type', o.type, { options: ['unknown', 'plus', 'classic'], linked_to_bluetooth: !!o.bt, band_type_set_by: 'you' });
    }
    if (o.bt) {
      E('binary_sensor', 'Nearby', o.near ? 'on' : 'off', { person: o.person, band: o.nfc || null, away_after_minutes: 35 });
      E('sensor', 'Last seen', min(o.seen), { device_class: 'timestamp', person: o.person, band: o.nfc || null, heard_by: o.closest, beacons: 412, first_seen: min(60 * 24 * 30), payload: '0x...' });
      E('sensor', 'Heard by', o.closest, { rssi: o.rssi, at: min(o.seen) });
      E('sensor', 'Closest', o.closestNow ? o.closest : 'unknown', { rssi: o.rssi, heard_in_last_20_minutes: o.by });
      E('sensor', 'Signal', o.rssi, { unit_of_measurement: 'dBm', device_class: 'signal_strength', heard_by: o.closest, by_source: o.by }, 'diagnostic');
      E('sensor', 'Battery', o.bat, { unit_of_measurement: '%', device_class: 'battery', raw: '0x48', changes: [] });
    }
  }
  function bandsAll() {
    band('dev_b1', "Morgan's MagicBand+", { nfc: '04-1A-2B-3C-4D-5E-01', person: 'Morgan', bt: 'mb-A1B2C3', type: 'plus', tap: 4, reader: 'Front Door Reader', scans: 212, near: true, seen: 3, closest: 'Kitchen Bridge', closestNow: true, rssi: -61, bat: 72, by: { 'Kitchen Bridge': -61, 'Office BP2': -79 } });
    band('dev_b2', 'Blue', { nfc: '04-1A-2B-3C-4D-5E-02', person: 'Morgan', label: 'Blue', type: 'classic', tap: 60 * 24 * 6, reader: 'Garage Reader', scans: 31 });
    band('dev_b3', "Casey's MagicBand+", { nfc: '04-2B-3C-4D-5E-6F-03', person: 'Casey', bt: 'mb-D4E5F6', type: 'plus', tap: 180, reader: 'Garage Reader', scans: 98, near: false, seen: 95, closest: 'Office BP2', closestNow: false, rssi: -84, bat: O.lowBattery ? 15 : 80, by: { 'Office BP2': -84 } });
    band('dev_b4', 'Old band', { nfc: '04-2B-3C-4D-5E-6F-04', person: 'Casey', label: 'Old band', type: O.bandTypesKnown ? 'classic' : 'unknown', tap: 60 * 24 * 20, reader: 'Front Door Reader', scans: 4 });
    band('dev_b5', "Alex's MagicBand", { nfc: '04-3C-4D-5E-6F-70-05', person: 'Alex', type: O.bandTypesKnown ? 'classic' : 'plus', tap: 60 * 30, reader: 'Front Door Reader', scans: 17, allowed: false });
    band('dev_b6', 'Dog walker', { nfc: '04-4D-5E-6F-70-81-06', person: 'Sam', label: 'Dog walker', type: 'classic', tap: 60 * 24 * 2, reader: 'Front Door Reader', scans: 9 });
    if (O.btOnly) band('dev_b7', 'MagicBand+ 7F3C', { bt: 'mb-7F3C11', type: 'plus', near: true, seen: 6, closest: 'Kitchen Bridge', closestNow: true, rssi: -70, bat: 98, by: { 'Kitchen Bridge': -70, 'Office BP2': -74 } });
  }

  // ---- bridges (magicband-bridge + magicband-addon, screek-bp2-poe + magicband-addon) ----
  function bridges() {
    const B = (id, name, model, area, o) => { dev(id, name, model, area); const p = slug(name), E = (dom, label, state, attrs, cat) => { if (!has(label)) return; ent(`${dom}.${p}_${slug(label)}`, state, Object.assign({ friendly_name: `${name} ${label}` }, attrs || {}), id, 'esphome', cat); };
      E('switch', 'Fast mode', o.fast ? 'on' : 'off', {}, 'config'); if (o.proxy != null) E('switch', 'Bluetooth proxy', o.proxy ? 'on' : 'off', {}, 'config');
      E('switch', 'Automatic updates', 'on', {}, 'config'); E('select', 'Time zone', 'Eastern (New York)', { options: TZ }, 'config');
      E('button', 'Wake bands', 'unknown'); E('button', 'Ping', 'unknown'); E('text', 'Command', '', {}); E('button', o.bp2 ? 'Reboot Device' : 'Restart', 'unknown', {}, 'diagnostic');
      if (o.wifi) E('sensor', 'Wi-Fi signal', o.wifi, { unit_of_measurement: 'dBm' }, 'diagnostic');
      E('sensor', o.bp2 ? 'Uptime' : 'Last restart', o.bp2 ? '3d 4h 12m' : min(60 * 24 * 9), {}, 'diagnostic');
      E('sensor', o.bp2 ? 'CPU Temperature' : 'CPU temperature', 47, { unit_of_measurement: '°C' }, 'diagnostic');
      E('sensor', o.bp2 ? 'Heap Free' : 'Free memory', 120000, {}, 'diagnostic');
      E('sensor', o.bp2 ? 'IP Address' : 'IP address', o.ip, {}, 'diagnostic'); if (o.wifi) E('sensor', 'Wi-Fi network', 'LakeviewNet', {}, 'diagnostic');
      E('update', 'Firmware', 'off', { installed_version: FW }, 'config'); };
    B('dev_br1', 'Kitchen Bridge', 'magicband-bridge', 'kitchen', { fast: false, proxy: O.bridgeProxy ? true : null, wifi: -52, ip: '10.20.30.51' });
    B('dev_br2', 'Office BP2', 'magicband-bp2-poe', 'office', { fast: true, proxy: null, bp2: true, ip: '10.20.30.52' });
  }

  if (O.readerFirst) { readers(); service(); } else { service(); readers(); }
  bandsAll(); bridges();
  // ---- other Home Assistant entities ----
  const X = (eid, state, attrs) => { states[eid] = { entity_id: eid, state, attributes: attrs, last_updated: min(10), last_changed: min(10) }; };
  X('person.morgan', 'home', { friendly_name: 'Morgan', user_id: 'u1' }); X('person.casey', 'not_home', { friendly_name: 'Casey', user_id: 'u2' }); X('person.jordan', 'home', { friendly_name: 'Jordan', user_id: 'u3' });
  if (O.cameras) X('camera.front_doorbell', 'idle', { friendly_name: 'Front doorbell' });
  X('alarm_control_panel.house_alarm', 'disarmed', { friendly_name: 'House alarm' });
  const ss = new Date(); ss.setHours(16, 52, 0, 0); if (ss < new Date()) ss.setDate(ss.getDate() + 1); const sr = new Date(); sr.setHours(7, 11, 0, 0); if (sr < new Date()) sr.setDate(sr.getDate() + 1);
  X('sun.sun', 'above_horizon', { next_setting: ss.toISOString(), next_rising: sr.toISOString(), friendly_name: 'Sun' });
  if (O.strangers) {
    dev('dev_plug', 'Kitchen kettle plug', 'Smart plug', 'kitchen', { manufacturer: 'Plugco' });
    ent('switch.kitchen_kettle', 'off', { friendly_name: 'Kitchen kettle' }, 'dev_plug', 'plugco');
    ent('button.front_door_reader_wipe', 'unknown', { friendly_name: 'Front Door Reader Factory reset' }, 'dev_r1', 'esphome', 'config');
    ent('button.front_door_reader_tidy', 'unknown', { friendly_name: 'Front Door Reader Tidy' }, 'dev_r1', 'esphome', 'config');
    entities['button.front_door_reader_tidy'].name = 'Forget all bands';
  }

  // ---- the integration's service responses ----
  const badge = (key, name, how, icon, earned) => ({ key, name, how, icon, earned: earned ? min(earned) : null });
  const BADGES = e => [badge('first', 'First tap', 'Your first tap in', '🎟️', e[0]), badge('taps_10', 'Regular', '10 taps', '🔟', e[1]), badge('taps_50', 'Frequent visitor', '50 taps', '⭐', e[2]), badge('taps_100', 'Century', '100 taps', '💯', e[3]), badge('taps_250', 'Super fan', '250 taps', '🌟'), badge('taps_500', 'Annual passholder', '500 taps', '🏰'), badge('taps_1000', 'Legend', '1,000 taps', '👑'), badge('early_bird', 'Early bird', 'A tap before 7 am', '🌅', e[4]), badge('night_owl', 'Night owl', 'A tap after 10 pm', '🦉'), badge('weekend', 'Weekender', 'Taps on a Saturday and the Sunday after', '🎡', e[5]), badge('streak_7', 'Week streak', 'Taps on 7 days in a row', '🔥', e[6]), badge('streak_30', 'Month streak', 'Taps on 30 days in a row', '🚀'), badge('holiday', 'Holiday tap', 'A tap on a holiday', '🎉'), badge('holidays_5', 'Holiday hopper', 'Taps on 5 different holidays', '🎊'), badge('birthday', 'Birthday tap', 'A tap on your birthday', '🎂', e[7]), badge('seasons', 'Four seasons', 'Taps in winter, spring, summer and autumn', '🍂')];
  const pp = (taps, days, st, best, e) => ({ taps, days, streak: st, best_streak: best, first: min(60 * 24 * 60), badges: BADGES(e) });
  const settings = { lockdown: !!O.lockdown, lockdown_away: false, lockdown_night: true, lockdown_from: '23:00', lockdown_until: '06:00', lockdown_alarm: null, holiday_shows: true, birthday_shows: true, passport: !!O.passport, passport_shows: true };
  const samPass = O.guestPass === 'expired' ? { from: iso(NOW - 86400e3 * 40), until: iso(NOW - 86400e3 * 2), uses_left: 0, access_from: '11:00', access_until: '14:00', days: ['mon', 'wed', 'fri'] }
    : { from: null, until: iso(NOW + 86400e3 * 30), uses_left: 12, access_from: '11:00', access_until: '14:00', days: ['mon', 'wed', 'fri'] };
  const LIST = () => ({
    people: [
      { id: 'a1b2c3d4e5f6', name: 'Alex', ha_person: null, allowed: false, welcome_colour: null, welcome_sound: null, bands: ['04-3C-4D-5E-6F-70-05'], birthday: '03-14', lockdown_exempt: false, guest: false, pass: null, allowed_now: false, passport: pp(17, 9, 0, 3, [900, 800]) },
      { id: 'b1b2c3d4e5f6', name: 'Casey', ha_person: 'person.casey', allowed: true, welcome_colour: 'Cyan', welcome_sound: null, bands: [], birthday: null, lockdown_exempt: false, guest: false, pass: null, allowed_now: true, passport: pp(102, 51, 2, 9, [9000, 8000, 5000, 100, 3000, 4000, 2000]) },
      { id: 'c1b2c3d4e5f6', name: 'Morgan', ha_person: 'person.morgan', allowed: true, welcome_colour: 'Purple', welcome_sound: O.welcomeSound ? 'castle-fanfare.mp3' : null, bands: [], birthday: '11-22', lockdown_exempt: true, guest: false, pass: null, allowed_now: true, passport: pp(243, 88, 12, 21, [9000, 8000, 5000, 1000, 3000, 4000, 2000, 5]) },
      { id: 'd1b2c3d4e5f6', name: 'Sam', ha_person: null, allowed: true, welcome_colour: null, welcome_sound: null, bands: [], birthday: null, lockdown_exempt: false, guest: O.guestPass !== 'none', pass: O.guestPass !== 'none' ? samPass : null, allowed_now: O.guestPass === 'none', passport: O.guestPass !== 'none' ? null : pp(9, 4, 1, 2, [3000]) },
    ],
    bands: [
      { band: '04-1A-2B-3C-4D-5E-01', person: 'Morgan', allowed: true, in_schedule: true },
      { band: '04-3C-4D-5E-6F-70-05', person: 'Alex', allowed: false, in_schedule: true },
      { band: '04-4D-5E-6F-70-81-06', person: 'Sam', label: 'Dog walker', allowed: true, access_from: '07:00', access_until: '19:00', access_days: ['mon', 'tue', 'wed', 'thu', 'fri'], expires: iso(NOW + 86400e3 * 60), in_schedule: true },
    ],
    readers: {}, enrolment: null, colours: COL, settings, lockdown: settings.lockdown ? ['by hand'] : [],
    today: { date: new Date().toISOString().slice(0, 10), holidays: [], birthdays: ['Morgan'] },
    upcoming: [{ key: 'thanksgiving', name: 'Thanksgiving', show: 'Thanksgiving', date: '2026-11-26' }, { key: 'hanukkah', name: 'Hanukkah', show: 'Hanukkah', date: '2026-12-05' }, { key: 'christmas', name: 'Christmas', show: 'Christmas', date: '2026-12-25' }, { key: 'new_year', name: 'New Year', show: 'New Year', date: '2027-01-01' }],
  });
  const BTL = () => ({ bluetooth_bands: [
    { id: 'mb-A1B2C3', name: "Morgan's MagicBand+", person: 'Morgan', band: '04-1A-2B-3C-4D-5E-01', nearby: true, last_seen: min(3), battery: 72, heard_by: 'Kitchen Bridge' },
    { id: 'mb-D4E5F6', name: "Casey's MagicBand+", person: 'Casey', band: '04-2B-3C-4D-5E-6F-03', nearby: false, last_seen: min(95), battery: O.lowBattery ? 15 : 80, heard_by: 'Office BP2' },
    ...(O.btOnly ? [{ id: 'mb-7F3C11', name: 'MagicBand+ 7F3C', person: null, band: null, nearby: true, last_seen: min(6), battery: 98, heard_by: 'Kitchen Bridge' }] : [])], encrypted_messages: 0, pairing: [] });
  const snap = 'data:image/svg+xml;utf8,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="320" height="240"><rect width="320" height="240" fill="#556"/><circle cx="160" cy="110" r="50" fill="#99a"/><text x="10" y="230" fill="#fff" font-size="14">mock camera</text></svg>');
  const HISTL = () => { const who = [["Morgan's MagicBand+", '04-1A-2B-3C-4D-5E-01', 'Morgan', 'Front Door Reader', true], ['04-99-88-77-66-55-44', '04-99-88-77-66-55-44', null, 'Garage Reader', false], ["Casey's MagicBand+", '04-2B-3C-4D-5E-6F-03', 'Casey', 'Garage Reader', true], ["Alex's MagicBand", '04-3C-4D-5E-6F-70-05', 'Alex', 'Front Door Reader', false], ['Dog walker', '04-4D-5E-6F-70-81-06', 'Sam', 'Front Door Reader', true]];
    return { taps: Array.from({ length: 27 }, (_, i) => { const w = who[i % who.length]; return { time: min(4 + i * 47), name: w[0], band: w[1], person: w[2], reader: w[3], allowed: w[4], enrolled: i === 9, badges: i === 0 ? ['Super fan'] : [], snapshot_url: O.cameras && w[3] === 'Front Door Reader' && i < 12 ? snap : undefined }; }), cameras: O.cameras ? { dev_r1: 'camera.front_doorbell' } : {}, snapshot_days: 30 }; };

  window.__calls = [];
  window.__mockReject = null;
  const reject = key => window.__mockReject && window.__mockReject.test(key) ? Promise.reject(new Error('MOCK-REJECT Reader not connected')) : null;
  const battHist = eid => { const v = +((hass.states[eid] || {}).state || 50); return Array.from({ length: 14 }, (_, i) => ({ s: String(Math.min(100, v + (13 - i) * 2)), lu: (NOW - (7 - i * 0.5) * 864e5) / 1000 })); };
  const hass = {
    states, entities, devices, areas, user: { is_admin: true, name: 'Morgan' }, language: 'en',
    callService(domain, service, data) { window.__calls.push(['svc', domain, service, data]);
      const r = reject(domain + '.' + service); if (r) return r;
      const s = hass.states[data.entity_id]; if (s && /turn_on|turn_off/.test(service)) s.state = service === 'turn_on' ? 'on' : 'off';
      if (s && service === 'select_option') s.state = data.option; if (s && service === 'set_value') s.state = String(data.value);
      if (s && service === 'volume_set') s.attributes = Object.assign({}, s.attributes, { volume_level: data.volume_level });
      if (s) setTimeout(() => window.__push && window.__push(), 50);   // Home Assistant pushes the new state
      return Promise.resolve({}); },
    callWS(msg) { window.__calls.push(['ws', msg.type, msg.domain, msg.service, msg.service_data]);
      if (msg.type === 'call_service') { const r0 = reject(msg.domain + '.' + msg.service); if (r0) return r0;
        const s = msg.service;
        if (s === 'history' && !O.history) return Promise.reject(new Error(O.historyError));
        const r = s === 'list' ? LIST() : s === 'list_bluetooth_bands' ? BTL() : s === 'history' ? HISTL() : {};
        return new Promise(res => setTimeout(() => res({ response: r }), 30)); }
      if (msg.type === 'history/history_during_period') { const o = {}; (msg.entity_ids || []).forEach(e => o[e] = battHist(e)); return Promise.resolve(o); }
      return Promise.resolve({}); },
    fetchWithAuth(url, o) { const m = (o && o.method) || 'GET'; window.__calls.push(['fetch', url, m]);
      if (url === '/api/magicband/page') return fetch(url);   // the harness serves the page panel.py builds
      const r = reject(m + ' ' + url); if (r) return r;
      if (m === 'GET') return Promise.resolve(new Response(new Blob(['x'], { type: 'audio/mpeg' }), { status: 200 }));
      return Promise.resolve(new Response(JSON.stringify({ ok: true }), { status: 200, headers: { 'Content-Type': 'application/json' } })); },
  };
  window.__mock = { hass, opts: O };
})();
