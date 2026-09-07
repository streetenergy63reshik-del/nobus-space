/* Deterministic UI unit checks. DOM/network doubles are NOT browser or live E2E evidence. */
const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const crypto = require("node:crypto");
const source = fs.readFileSync(path.join(__dirname, "../../src/transport/miniapp_static/app.js"), "utf8");
const A = "aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa", B = "bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb";
const token = "b".repeat(40), challenge = "c".repeat(40);
const task = (id=A, revision=1, extra={}) => ({task_id:id, description:id===A?"Первая задача":"Вторая задача",
  task_revision:revision, result_revision:0, result_digest:null, status:"working", status_label:"В работе",
  terminal:false, created_at:"2026-09-07T10:00:00Z", updated_at:"2026-09-07T10:00:00Z", ...extra});
class Element {
  constructor(tag="div") { this.tagName=tag; this.children=[]; this.listeners={}; this.hidden=false; this.open=false; this.value=""; this.disabled=false; this._text=""; this.attrs={}; }
  set textContent(value) { this._text=String(value); this.children=[]; }
  get textContent() { return this._text + this.children.map(x=>x.textContent).join(""); }
  get firstChild() { return this.children[0]; }
  replaceChildren(...nodes) { this._text=""; this.children=nodes; }
  append(...nodes) { this.children.push(...nodes); }
  addEventListener(name, callback) { this.listeners[name]=callback; }
  setAttribute(name,value) { this.attrs[name]=value; }
  closest() { return this.label ||= new Element("label"); }
  focus() { this.focused=true; }
  showModal() { this.open=true; }
  close() { this.open=false; this.listeners.close?.(); }
  remove() { this.removed=true; }
  click() { return this.listeners.click?.(); }
}
const json = (body,status=200) => new Response(JSON.stringify(body),{status,headers:{"Content-Type":"application/json"}});
const flush = async () => { for(let i=0;i<20;i++) await new Promise(setImmediate); };
function harness(handler=()=>undefined, storage=new Map()) {
  const nodes=new Map(), calls=[], timers=new Map(), blobs=[], revoked=[], clipboard=[];
  let timerId=0;
  const $=(id)=>{ if(!nodes.has(id)) nodes.set(id,new Element()); return nodes.get(id); };
  const context = vm.createContext({
    document:{querySelector:s=>$(s.slice(1)), createElement:t=>new Element(t), createDocumentFragment:()=>new Element(),
      body:new Element("body"), addEventListener(){}, createRange:()=>({selectNodeContents(){}})},
    window:{Telegram:{WebApp:{initData:"synthetic-test-initData",ready(){},expand(){},close(){}}},addEventListener(){},getSelection:()=>({removeAllRanges(){},addRange(){}})},
    navigator:{onLine:true, clipboard:{writeText:async x=>clipboard.push(x)}},
    localStorage:{getItem:k=>storage.get(k)??null,setItem:(k,v)=>storage.set(k,String(v)),removeItem:k=>storage.delete(k)},
    crypto:crypto.webcrypto, Response, Blob, AbortController, Uint8Array, Intl, Date,
    URL:{createObjectURL:b=>{blobs.push(b);return "blob:synthetic";},revokeObjectURL:u=>revoked.push(u)},
    setTimeout:(fn,ms)=>{timers.set(++timerId,{fn,ms});return timerId;}, clearTimeout:id=>timers.delete(id),
    fetch:async (url,options={})=>{
      calls.push({url,options});
      const custom=await handler(url,options,calls);
      if(custom!==undefined) return custom;
      if(url==="/api/session/recover") return json({access_token:token,expires_in:120});
      if(url==="/api/tasks?limit=20") return json({tasks:[task(A),task(B)]});
      if(url.includes("/events?")) return json({events:[]});
      if(url==="/api/tasks/"+A) return json(task(A));
      if(url==="/api/tasks/"+B) return json(task(B));
      return json({detail:"missing"},404);
    },
  });
  vm.runInContext(source,context);
  return {$,calls,timers,storage,blobs,revoked,clipboard,run:s=>vm.runInContext(s,context)};
}
test("transient read failure retains task, selection and bearer",async()=>{
  let fail=false;
  const h=harness((url)=>fail&&url==="/api/tasks/"+A?json({},503):undefined);
  await flush(); h.run('selectTask("'+A+'")'); await flush();
  fail=true; await h.run("refresh()");
  assert.match(h.$("detail-title").textContent,/Первая/);
  assert.equal(h.run("selectedTaskId"),A); assert.equal(h.run("bearer"),token);
  assert.match(h.$("state").textContent,/Повторить чтение/);
});
test("late response from old selection never replaces selected task",async()=>{
  let resolve;
  const h=harness(url=>url==="/api/tasks/"+A?new Promise(r=>resolve=r):undefined);
  await flush(); h.run('selectTask("'+A+'")'); await flush();
  h.run('selectTask("'+B+'")'); await flush(); resolve(json(task(A))); await flush();
  assert.equal(h.$("detail-title").textContent,"Вторая задача");
});
test("ACK loss reconciles one persisted request; no blind mutation replay",async()=>{
  let key, posts=0;
  const storage=new Map();
  const handler=(url,options)=>{
    if(url==="/api/tasks"&&options.method==="POST"){posts++;key=options.headers["Idempotency-Key"];throw new TypeError("offline");}
    if(url.startsWith("/api/requests/")) return json({request_id:key,state:"accepted",task_id:A,status:"queued"});
  };
  const h=harness(handler,storage);await flush();h.$("instruction").value="Синтетический текст";h.$("display-title").value="Тест";
  await h.run("createTask({preventDefault(){}})");await flush();
  assert.equal(posts,1);assert.equal(h.run("selectedTaskId"),A);assert.equal(storage.has("nobus.pending"),false);
  assert.ok([...storage.values()].every(x=>x!==token&&!x.includes("Синтетический")));
});
test("unknown POST remains read-only after reload and blocks duplicate submit",async()=>{
  const key="dddddddd-dddd-4ddd-dddd-dddddddddddd";
  const storage=new Map([["nobus.pending",key]]);
  const h=harness(()=>undefined,storage);await flush();
  h.$("instruction").value="Любой текст";h.$("display-title").value="Тест";
  await h.run("createTask({preventDefault(){}})");
  assert.equal(h.calls.filter(x=>x.url==="/api/tasks").length,0);
  assert.equal(h.$("new-task").disabled,true);assert.match(h.$("state").textContent,/Проверить приём/);
});
test("clarification survives reload using only original opaque marker",async()=>{
  const key="eeeeeeee-eeee-4eee-eeee-eeeeeeeeeeee";
  const storage=new Map([["nobus.pending",key]]);
  const handler=url=>url.startsWith("/api/requests/")?json({request_id:key,state:"clarification",question:"Какой период?",clarification_token:challenge}):undefined;
  const h=harness(handler,storage);await flush();
  assert.equal(h.$("clarification-question").textContent,"Какой период?");
  assert.equal(h.$("submit-task").textContent,"Ответить");assert.ok(![...storage.values()].includes(challenge));
  const reloaded=harness(handler,storage);await flush();
  assert.equal(reloaded.$("clarification-question").textContent,"Какой период?");
  assert.equal(reloaded.run("clarification"),challenge);
});
test("expired read does one Core recovery and one retry, never a loop",async()=>{
  let read=0,recover=0;
  const h=harness(url=>{
    if(url==="/api/session/recover"){recover++;return json({access_token:token,expires_in:120});}
    if(url==="/api/tasks/"+A){read++;return json({},401);}
  });
  await flush();h.run('selectTask("'+A+'")');await flush();
  assert.equal(read,2);assert.equal(recover,2);assert.equal(h.run("bearer"),null);
  assert.match(h.$("state").textContent,/Сессия завершена/);
});
test("unknown result revision fails closed and never shows result",async()=>{
  const h=harness(url=>{
    if(url==="/api/tasks/"+A)return json(task(A,2,{has_verified_answer:true,result_revision:2,result_digest:"sha256:"+"a".repeat(64)}));
    if(url.includes("/result?"))return json({task_id:A,task_revision:2,result_revision:1,result_digest:"sha256:"+"a".repeat(64),answer:"STALE"});
  });
  await flush();h.run('selectTask("'+A+'")');await flush();
  assert.ok(!h.$("detail").textContent.includes("STALE"));assert.match(h.$("state").textContent,/Повторить чтение/);
});
test("HTML is text; bidi/control characters are removed",async()=>{
  const h=harness();await flush();
  const value=h.run('element("p","","<img src=x onerror=alert(1)>\\u202e\\u0001")');
  assert.equal(value.textContent,"<img src=x onerror=alert(1)>");assert.equal(value.children.length,0);
});
test("terminal result stops compute polling, pending delivery keeps bounded reads",async()=>{
  let delivery=false;
  const h=harness(url=>url==="/api/tasks/"+A?json(task(A,1,{terminal:true,status:"ready",delivery_pending:delivery})):undefined);
  await flush();h.run('selectTask("'+A+'")');await flush();
  assert.equal([...h.timers.values()].filter(x=>x.ms===3000).length,0);
  delivery=true;await h.run("refresh()");
  assert.equal([...h.timers.values()].filter(x=>x.ms===3000).length,1);
});
test("download verifies bytes before browser save and revokes object URL",async()=>{
  const bytes=Buffer.from("Синтетический результат");
  const digest="sha256:"+crypto.createHash("sha256").update(bytes).digest("hex");
  const h=harness(url=>url.includes("/artifacts/")?new Response(bytes):undefined);await flush();
  h.run('selectedTaskId="'+A+'";selectionGeneration=5');
  const artifact={artifact_id:B,filename:"nobus-result.txt",media_type:"text/plain; charset=utf-8",size:bytes.length,content_digest:digest};
  h.run("globalThis.testFile="+JSON.stringify(artifact));
  await h.run('downloadArtifact("'+A+'",{result_revision:1},testFile,5,document.createElement("button"),document.createElement("p"))');
  assert.equal(h.blobs.length,1);
  [...h.timers.values()].filter(x=>x.ms===1000).forEach(x=>x.fn());assert.equal(h.revoked.length,1);
  h.run('testFile.content_digest="sha256:"+"0".repeat(64)');
  await h.run('downloadArtifact("'+A+'",{result_revision:1},testFile,5,document.createElement("button"),document.createElement("p"))');
  assert.equal(h.blobs.length,1);
});
test("double submit sends one POST while first response is delayed",async()=>{
  let resolve,posts=0;
  const h=harness((url,options)=>{
    if(url==="/api/tasks"&&options.method==="POST"){posts++;return new Promise(r=>resolve=r);}
  });
  await flush();h.$("instruction").value="Текст";h.$("display-title").value="Название";
  const first=h.run("createTask({preventDefault(){}})");await flush();
  await h.run("createTask({preventDefault(){}})");assert.equal(posts,1);
  resolve(json({task_id:A,status:"queued"},202));await first;
});
