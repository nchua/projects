/**
 * Fitness app → Google Sheet mirror.
 *
 * Pulls GET /export/workouts from the backend every hour and rewrites one tab
 * per table (Weekly Volume, Weekly Muscle Volume, Sessions, Sets, PRs,
 * Bodyweight) plus an About tab with the last refresh time.
 *
 * Setup (once):
 *   1. Set EXPORT_TOKEN on the Railway backend service (32+ random chars).
 *   2. New Google Sheet → Extensions → Apps Script → paste this file → Save.
 *   3. Reload the Sheet, then Fitness → "Set export token" and paste the token.
 *      (Anyone with edit access to this Sheet can read it; share view-only.)
 *   4. Fitness → "Refresh now" (approve the permission prompt), then
 *      Fitness → "Refresh hourly".
 *
 * The token lives in Script Properties, never in a cell.
 *
 * @OnlyCurrentDoc  Limits this script's Google access to this one Sheet.
 */

const BASE_URL = 'https://backend-production-e316.up.railway.app';
const DAYS = 365;

// Tab name → response key. Column order follows the backend's field order.
const TABS = [
  ['Weekly Volume', 'weekly_volume'],
  ['Weekly Muscle Volume', 'weekly_muscle_volume'],
  ['Sessions', 'sessions'],
  ['Sets', 'sets'],
  ['PRs', 'prs'],
  ['Bodyweight', 'bodyweight'],
];

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Fitness')
    .addItem('Refresh now', 'refresh')
    .addItem('Refresh hourly', 'installTrigger')
    .addItem('Set export token', 'setToken')
    .addToUi();
}

function setToken() {
  const ui = SpreadsheetApp.getUi();
  const answer = ui.prompt('Export token', 'Paste the EXPORT_TOKEN value from Railway.', ui.ButtonSet.OK_CANCEL);
  if (answer.getSelectedButton() !== ui.Button.OK) return;
  PropertiesService.getScriptProperties().setProperty('EXPORT_TOKEN', answer.getResponseText().trim());
}

function installTrigger() {
  ScriptApp.getProjectTriggers()
    .filter(function (t) { return t.getHandlerFunction() === 'refresh'; })
    .forEach(function (t) { ScriptApp.deleteTrigger(t); });
  ScriptApp.newTrigger('refresh').timeBased().everyHours(1).create();
}

function refresh() {
  const token = PropertiesService.getScriptProperties().getProperty('EXPORT_TOKEN');
  if (!token) throw new Error('No export token. Use Fitness → Set export token.');

  const response = UrlFetchApp.fetch(BASE_URL + '/export/workouts?days=' + DAYS, {
    headers: { Authorization: 'Bearer ' + token },
    muteHttpExceptions: true,
  });
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  if (response.getResponseCode() !== 200) {
    // Leave the last good data in place; record the failure where a reader sees it.
    writeAbout_(ss, null, 'FAILED: HTTP ' + response.getResponseCode() + ' at ' + new Date().toISOString());
    throw new Error('Export failed: HTTP ' + response.getResponseCode());
  }

  const data = JSON.parse(response.getContentText());
  TABS.forEach(function (tab) { writeTable_(ss, tab[0], data[tab[1]] || []); });
  writeAbout_(ss, data, 'OK');
}

function writeTable_(ss, name, rows) {
  const sheet = ss.getSheetByName(name) || ss.insertSheet(name);
  sheet.clearContents();
  if (!rows.length) {
    sheet.getRange(1, 1).setValue('(no rows)');
    return;
  }
  const headers = Object.keys(rows[0]);
  const values = [headers].concat(rows.map(function (row) {
    return headers.map(function (h) { return row[h] === null ? '' : row[h]; });
  }));
  // Date columns are forced to plain text so they stay ISO (YYYY-MM-DD)
  // instead of being locale-reformatted; everything else stays numeric.
  sheet.getRange(1, 1, values.length, headers.length).setNumberFormat('General');
  headers.forEach(function (h, i) {
    if (h === 'day' || h === 'week_start') {
      sheet.getRange(1, i + 1, values.length, 1).setNumberFormat('@');
    }
  });
  sheet.getRange(1, 1, values.length, headers.length).setValues(values);
  sheet.setFrozenRows(1);
}

function writeAbout_(ss, data, status) {
  const sheet = ss.getSheetByName('About') || ss.insertSheet('About', 0);
  const rows = [['last_refresh_status', status]];
  if (data) {
    rows.push(
      ['generated_at_utc', data.generated_at],
      ['window_start', data.start],
      ['window_end', data.end],
      ['units', 'Weights and tonnage are lb. Days are the local calendar day. Weeks start Monday.'],
      ['volume_rule', 'Tonnage and working_sets exclude warm-up sets. Sets tab lists warm-ups with volume_lb 0. Bodyweight sets count added load only.'],
      ['source', 'Fitness app backend on Railway, GET /export/workouts. Refreshed hourly.']
    );
    sheet.clearContents();
  }
  sheet.getRange(1, 1, rows.length, 2).setNumberFormat('@').setValues(rows);
}
