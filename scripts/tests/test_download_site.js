const assert = require('node:assert/strict');
const test = require('node:test');
const select = require('../../website/releases');
const tag='build-'+ 'a'.repeat(40), base='https://github.com/MeticulousTransformer/CapForge/releases/download/'+tag+'/';
function release(){return {tag_name:tag, assets:['CapForge-0.3.3-macOS.dmg','CapForge-0.3.3-Windows.exe'].map(name=>({name,browser_download_url:base+name}))};}
test('download page uses only the complete official same-version platform pair',()=>{assert.equal(select(release()).version,'0.3.3');for(const change of [r=>r.draft=true,r=>r.assets.pop(),r=>r.assets[1].name='CapForge-0.3.4-Windows.exe',r=>r.assets[0].browser_download_url='https://example.com/installer',r=>r.assets.push(r.assets[0])]){let r=release();change(r);assert.equal(select(r),null);}});
