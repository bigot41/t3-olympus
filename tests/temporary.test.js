const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

function fixture(storage = new Map()) {
  let tick, name = 'Temporary', host = true, thread = 'temp-1';
  const posts = [], timers = [];
  const button = { attrs: {}, setAttribute(k,v) { this.attrs[k]=v; }, getAttribute(k) { return this.attrs[k]; } };
  const root = { setAttribute() {}, removeAttribute() {}, toggleAttribute() {} };
  let normal = false;
  const option = { querySelectorAll: () => [{ textContent: 'Projects', children: [] }, { textContent: 'C:/Projects', children: [] }], removeAttribute() {}, toggleAttribute() {}, click() { name='Projects'; thread=null; normal=false; ctx.location.hash='#/draft/normal'; } };
  const fresh = { after() {}, click() { normal=true; } };
  const ctx = {
    location: { hash: '#/env/temp-1' }, CSS: { escape: x=>x },
    sessionStorage: { getItem: k=>storage.get(k), setItem: (k,v)=>storage.set(k,v), removeItem: k=>storage.delete(k) },
    localStorage: { getItem: ()=>'Projects', setItem() {} },
    performance: { now: ()=>0 }, requestAnimationFrame: fn=>fn(),
    setTimeout: (fn, ms)=>{ timers.push({fn,ms}); },
    fetch: async ()=>({json: async()=>({threads:['temp-1']})}),
    olympusAbove() {},
    document: {
      head: { append() {} }, documentElement: root,
      createElement: ()=>({}), getElementById: id=>id==='olympus-temp-button'?button:null,
      querySelectorAll: selector=>selector==='[role="option"]' && normal ? [option]:[],
      querySelector: selector=> {
        if (selector.includes('breadcrumb')) return {textContent:name};
        if (selector.includes('composer')) return host?{}:null;
        if (selector.includes('data-thread-item')) return name==='Temporary' && thread==='temp-1'?{}:null;
        if (selector.includes('New thread')) return fresh;
        return null;
      },
    },
    olympus: { HELPER:'helper', COMPOSER:'composer', threadId:()=>thread, onDom: fn=>{tick=fn;}, box:()=>null, post: async (path,body)=>{posts.push({path,body});return {ok:false};} },
  };
  ctx.window=ctx;ctx.top=ctx;ctx.addEventListener=()=>{};
  vm.runInNewContext(fs.readFileSync('temporary.js','utf8'), ctx);
  return {ctx, posts, storage, timers, tick:()=>tick(), navigate(hash, project, id, composer=true) {ctx.location.hash=hash; name=project;thread=id;host=composer;tick();}, button,
    async leave() { // Install the real click handler through the script's button creation.
      ctx.document.getElementById=()=>null;
      ctx.document.createElement=()=>button;
      tick();
      button.onclick({stopPropagation(){}});
      for(let i=0;i<12;i++) await Promise.resolve();
    }
  };
}

test('Usage and return keep the conversation and temporary mode without deletion',()=>{
 const f=fixture(); f.tick();
 f.navigate('#/settings/usage',null,null,false);
 assert.equal(f.posts.length,0);
 assert.equal(f.button.attrs['aria-pressed'],'true');
 f.navigate('#/draft/normal','Projects',null);
 assert.equal(f.ctx.location.hash,'#/env/temp-1');
 assert.equal(f.posts.length,0);
});
test('reload on Usage preserves active temporary route and startup cleanup excludes it',async()=>{
 const f=fixture();f.tick();
 const g=fixture(f.storage);
 g.navigate('#/settings/usage',null,null,false);
 await g.timers.find(t=>t.ms===3000).fn();
 assert.equal(g.posts.length,0);
 g.navigate('#/','Projects',null);
 assert.equal(g.ctx.location.hash,'#/env/temp-1');
});
test('explicit leave deletes the temporary thread and permits normal chat',async()=>{
 const f=fixture();f.tick();await f.leave();
 assert.equal(f.ctx.location.hash,'#/draft/normal');
 assert.equal(f.storage.has('olympus:temporary'),false);
 assert.equal(f.posts[0].path,'/temporary/leaving');
 f.navigate('#/draft/normal','Projects',null);
 assert.equal(f.ctx.location.hash,'#/draft/normal');
});
