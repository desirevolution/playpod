import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import ts from 'typescript';
import {t, setLanguage, getLocale, detectLocale, readPreference, localeTag} from '../src/i18n.ts';
import {english} from '../src/messages.ts';

test('language detection honors browser priority and falls back to English',()=>{
  assert.equal(detectLocale(['fr-FR','de-AT','en']), 'de');
  assert.equal(detectLocale(['en-US','de-DE']), 'en');
  assert.equal(detectLocale(['de']), 'de');
  assert.equal(detectLocale(['fr']), 'en');
});
test('language is persisted and interpolation stays plain text',()=>{
  const storage=globalThis.localStorage;const data=new Map();
  globalThis.localStorage={getItem:k=>data.get(k),setItem:(k,v)=>data.set(k,v)};
  try{
    setLanguage('en');assert.equal(readPreference(),'en');assert.equal(getLocale(),'en');assert.equal(localeTag(),'en-GB');
    assert.equal(t('Einschlafen starten'),'Start sleep mode');
    assert.equal(t('{count} Downloads vorgemerkt.',{count:2}),'2 downloads queued.');
    assert.equal(t('Die Audiodatei von „{title}“ wird gelöscht. Episode, Merker und Hörfortschritt bleiben erhalten.',{title:'<script>test</script>'}).includes('<script>test</script>'),true);
    setLanguage('de');assert.equal(t('Einschlafen starten'),'Einschlafen starten');assert.equal(localeTag(),'de-DE');
  }finally{setLanguage('de');globalThis.localStorage=storage;}
});
test('all translated source messages have English text and matching placeholders',()=>{
  const placeholders=s=>[...s.matchAll(/\{(\w+)\}/g)].map(m=>m[1]).sort();
  for(const [key,value] of Object.entries(english)){
    assert.ok(value.trim(),key);assert.deepEqual(placeholders(key),placeholders(value),key);
  }
  const root=fileURLToPath(new URL('../src/',import.meta.url));
  function files(dir){return fs.readdirSync(dir,{withFileTypes:true}).flatMap(e=>e.isDirectory()?files(path.join(dir,e.name)):[path.join(dir,e.name)]);}
  for(const file of files(root).filter(f=>f.endsWith('.ts')&&!f.endsWith('messages.ts'))){
    const source=ts.createSourceFile(file,fs.readFileSync(file,'utf8'),ts.ScriptTarget.Latest,true);
    function walk(node){
      if(ts.isCallExpression(node)&&node.expression.getText(source)==='t'&&node.arguments[0]&&ts.isStringLiteral(node.arguments[0])){
        const key=node.arguments[0].text.replace(/\s+/g,' ').trim();assert.ok(key in english,`${file}: missing ${key}`);
      }
      ts.forEachChild(node,walk);
    }
    walk(source);
  }
});

test('known errors switch language while external diagnostics stay unchanged',async()=>{
  const {localizeMessage}=await import('../src/i18n.ts');
  try {
    setLanguage('en');assert.equal(localizeMessage('MPD nicht erreichbar oder Befehl fehlgeschlagen'),'MPD unreachable or command failed');
    assert.equal(localizeMessage('MPD konnte die Episode nach der Modusansage nicht fortsetzen: ACK 50'),'MPD could not resume after the announcement: ACK 50');
    assert.equal(localizeMessage('HTTP 403 from media.example'),'HTTP 403 from media.example');
    assert.equal(localizeMessage('constructor'),'constructor');
    assert.equal(t('toString'),'toString');
    setLanguage('de');assert.equal(localizeMessage('The queue is empty'),'Warteschlange ist leer');
  } finally { setLanguage('de'); }
});

test('offline notice respects saved language without loading the application',async()=>{
  const vm=await import('node:vm');
  const html=fs.readFileSync(new URL('../public/offline.html',import.meta.url),'utf8');
  const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
  for(const [saved,languages,expected] of [['en',['de-DE'],'en'],['de',['en-US'],'de'],['auto',['en-US'],'en']]){
    const elements=[{dataset:{en:'No connection to PlayPod'},textContent:'Keine Verbindung zu PlayPod'}];
    const document={title:'PlayPod',documentElement:{lang:'de'},querySelectorAll:()=>elements};
    vm.runInNewContext(script,{document,navigator:{languages},localStorage:{getItem:()=>saved}});
    assert.equal(document.documentElement.lang,expected);
    assert.equal(elements[0].textContent,expected==='en'?'No connection to PlayPod':'Keine Verbindung zu PlayPod');
  }
});


test('episode counts use singular and plural in both languages',async()=>{
  const {countText}=await import('../src/i18n.ts');
  try{setLanguage('en');assert.equal(countText(1,'{count} Episode','{count} Episoden'),'1 episode');assert.equal(countText(2,'{count} Episode','{count} Episoden'),'2 episodes');setLanguage('de');assert.equal(countText(1,'{count} Episode','{count} Episoden'),'1 Episode');}finally{setLanguage('de');}
});
