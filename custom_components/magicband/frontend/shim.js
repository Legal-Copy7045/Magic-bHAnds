/* MagicbHAnds live-data shim (a cut-down copy of the home-dashboards project's shim.js).
   The panel (panel.js) hands this frame the user's live `hass` object; this gives the page window.hdHA: states,
   entity and device metadata, and a deliberately small set of controls. */
(function () {
  'use strict';
  function getHass() { try { return window.parent && window.parent !== window ? window.parent.__mbHass : null; } catch (e) { return null; } }
  function lc(s) { return String(s || '').replace(/[‘’]/g, "'").toLowerCase().trim(); }
  var subs = [], spend = null;
  // the panel calls this whenever Home Assistant's state changes; coalesce bursts
  window.__mbOnHass = function () {
    if (spend || !subs.length) return;
    spend = setTimeout(function () { spend = null; subs.forEach(function (cb) { try { cb(); } catch (e) { console.error('[magicbhands] update failed', e); } }); }, 150);
  };
  /* Only these domains and services can be called from the page (the MagicBand bridges' and readers' settings), and
     whole-integration actions only from the MagicbHAnds integration itself. */
  var CTRL = { light: ['turn_on', 'turn_off', 'toggle'], switch: ['turn_on', 'turn_off', 'toggle'],
               media_player: ['volume_set'], select: ['select_option'], number: ['set_value'], button: ['press'] };
  var SVC = { magicband: ['assign_band', 'unassign_band', 'remove_band', 'add_person', 'update_person', 'remove_person',
                          'link_bluetooth', 'unlink_bluetooth', 'sync', 'send', 'list', 'list_bluetooth_bands',
                          'set_band_access', 'enrol', 'stop_enrolment', 'history', 'set_reader_camera'] };
  var NOPRESS = /factory_reset|safe_mode|forget_all/;   // buttons the page may not press
  var idxFor = null, idx = {};
  function nameIndex(h) {
    if (idxFor === h.states) return idx;
    idx = {}; idxFor = h.states;
    for (var eid in h.states) { var k = lc((h.states[eid].attributes || {}).friendly_name); (idx[k] = idx[k] || []).push(eid); }
    return idx;
  }
  window.hdHA = {
    live: function () { var h = getHass(); return !!(h && h.states && h.callService); },
    state: function (eid) { var h = getHass(); return (h && h.states && h.states[eid]) || null; },
    find: function (name, doms) {
      var h = getHass(); if (!h || !h.states) return null;
      var best = null, bs = -1;
      (nameIndex(h)[lc(name)] || []).forEach(function (eid) {
        var di = doms ? doms.indexOf(eid.split('.')[0]) : 0; if (di < 0) return;
        var sc = (h.states[eid].state !== 'unavailable' ? 100 : 0) + (doms ? doms.length - di : 0);
        if (sc > bs) { bs = sc; best = eid; }
      });
      return best;
    },
    call: function (domain, service, eid, data) {
      var h = getHass(); if (!h || !h.callService) return Promise.reject(new Error('Home Assistant is not connected'));
      if (String(eid).split('.')[0] !== domain || !CTRL[domain] || CTRL[domain].indexOf(service) < 0) return Promise.reject(new Error('not allowed: ' + domain + '.' + service));
      if (domain === 'button' && NOPRESS.test(eid)) return Promise.reject(new Error('not allowed from this page: ' + eid));
      var d = { entity_id: eid }; for (var k in (data || {})) d[k] = data[k];
      return h.callService(domain, service, d);
    },
    subscribe: function (cb) { subs.push(cb); return function () { subs = subs.filter(function (x) { return x !== cb; }); }; },
    all: function () { var h = getHass(); return (h && h.states) || {}; },
    meta: function (eid) {
      var h = getHass(); if (!h) return {};
      var e = (h.entities && h.entities[eid]) || {}, d = e.device_id && h.devices ? h.devices[e.device_id] : null;
      var a = e.area_id || (d && d.area_id);
      return { platform: e.platform, category: e.entity_category, hidden: !!e.hidden, device_id: e.device_id || null,
               device: d ? (d.name_by_user || d.name) : null, area: a && h.areas && h.areas[a] ? h.areas[a].name : null,
               area_id: a || null, name: e.name || null };
    },
    service: function (domain, service, data, resp) {
      var h = getHass(); if (!h || !h.callWS) return Promise.reject(new Error('Home Assistant is not connected'));
      if (!SVC[domain] || SVC[domain].indexOf(service) < 0) return Promise.reject(new Error('not allowed: ' + domain + '.' + service));
      return h.callWS({ type: 'call_service', domain: domain, service: service, service_data: data || {}, return_response: !!resp })
        .then(function (r) { return resp ? (r && r.response) : r; });
    },
    devices: function () {
      var h = getHass(), out = []; if (!h || !h.devices) return out;
      for (var k in h.devices) { var d = h.devices[k];
        out.push({ id: d.id, name: d.name, name_by_user: d.name_by_user || null, model: d.model || null, manufacturer: d.manufacturer || null,
                   area: d.area_id && h.areas && h.areas[d.area_id] ? h.areas[d.area_id].name : null }); }
      return out;
    },
    // history and logbook, read-only
    ws: function (msg) {
      var h = getHass(); if (!h || !h.callWS) return Promise.reject(new Error('Home Assistant is not connected'));
      var ok = ['history/history_during_period', 'logbook/get_events'];
      if (!msg || ok.indexOf(msg.type) < 0) return Promise.reject(new Error('not allowed: ' + (msg && msg.type)));
      return h.callWS(msg);
    }
  };
})();
