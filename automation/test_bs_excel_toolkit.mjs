// Tests for B/S Excel Toolkit's XLSX worksheet target normalization.
// No network calls or dependencies: built-in Node.js modules only.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext, Script } from 'node:vm';

const html = readFileSync(new URL('../apps/BS_Excel_Toolkit_1_0_0.html', import.meta.url), 'utf8');
const match = html.match(/function safePath\(target\)\{[^\r\n]+\}/);
assert.ok(match, 'Reusable workbook path resolver must exist');
const safePath = runInNewContext('(' + match[0] + ')', { URL, decodeURIComponent });

const cases = [
  ['worksheets/sheet1.xml', 'xl/worksheets/sheet1.xml'],
  ['./worksheets/sheet2.xml', 'xl/worksheets/sheet2.xml'],
  ['worksheets/../worksheets/sheet3.xml', 'xl/worksheets/sheet3.xml'],
  ['/xl/worksheets/sheet4.xml', 'xl/worksheets/sheet4.xml'],
  ['../xl/worksheets/sheet5.xml', 'xl/worksheets/sheet5.xml'],
  ['https://external.test/sheet.xml', null],
  ['//external.test/sheet.xml', null],
  ['../../../external.xml', null],
];
for (const [target, expected] of cases) {
  assert.equal(safePath(target), expected, 'Incorrect resolution: ' + target);
}

// Verify deletion uses the SAME resolver as workbook reading.
// A missing/malformed relationship must not remove the worksheet entry.
const warningBlock = html.match(/if\(opts\.removeWarning\)\{[^\r\n]+/);
assert.ok(warningBlock, 'Warning-sheet removal branch is missing');
const logic = warningBlock[0];
assert.ok(logic.includes("safePath(r.getAttribute('Target')"), 'Must normalize relationship target');
assert.ok(logic.includes("resolved.startsWith('xl/worksheets/')"), 'Must limit removal to worksheet parts');
assert.ok(logic.includes('zip.file(resolved)'), 'Must ensure the target exists in ZIP');
const guardedStart = logic.indexOf("if(resolved&&resolved.startsWith(");
const removed = logic.indexOf('sh.remove()', guardedStart);
assert.ok(guardedStart >= 0 && removed > guardedStart, 'Sheet removal must require validated relationship');
assert.ok(!logic.includes("target.startsWith('/')?"), 'Old manual resolution must not be reused');

// Ensure inline JavaScript stays syntactically valid after editing the HTML.
const inlineScripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)];
let parsed = 0;
for (const [, script] of inlineScripts) {
  if (!script.trim()) continue;
  new Script(script);
  parsed++;
}
assert.ok(parsed >= 1, 'No inline scripts parsed');
console.log('B/S Excel Toolkit: ' + cases.length + ' path cases, deletion guard, and ' + parsed + ' inline scripts OK.');
