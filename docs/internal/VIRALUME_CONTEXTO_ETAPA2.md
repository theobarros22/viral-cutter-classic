# VIRALUME STUDIO — Contexto Completo para Continuação (Etapa 2)

## OBJETIVO DO PROJETO

Construir o **Viralume Studio** — app web completo de edição de legendas para vídeo (vanilla HTML/JS/CSS + Python `http.server` porta 8766). Arquivo principal: `D:\CORTE VIRAL\studio\index.html`.

---

## STATUS ATUAL

- **Etapa 1**: ✅ Concluída e validada — Store IIFE com eventos, IDs estáveis, proxies de compat, localStorage
- **Etapa 2 (HTML/CSS)**: ✅ Concluída — CSS de seleção, batchBar, confirmModal, ppMultiNote injetados no arquivo
- **Etapa 2 (JavaScript)**: ✅ Concluída — script atualizado com suporte a multisseleção, sincronização CSS e barra de lote
- **Etapa 3 (Undo/Redo)**: ✅ Concluída — histórico de 100 ações, atalhos Ctrl+Z/Shift+Ctrl+Z/Ctrl+Y, agrupamento inteligente de drags de sliders e edição de texto
- **Etapa 6 (Command palette & Safe areas)**: ✅ Concluída — command palette (Ctrl+K), safe area overlays e validação pré-export implementadas

---

## REGRAS CRÍTICAS (NÃO VIOLAR)

1. **Identidade visual**: tema escuro, acentos laranja, preview vertical
2. **Layout**: biblioteca estilos à esquerda | transcrição centro | cartões ao lado | propriedades+preview à direita | timeline inferior
3. **Não remover**: drag-drop vídeo, Faster Whisper, estilos visuais, edição tempo real, sliders, chips Z/SFX/EM, Web Audio, atalhos, importar/exportar SRT, FFmpeg, NVENC, Aplicar para todos, Dividir por pausa, timeline clicável

---

## ETAPA 2 — SPEC APROVADA

### 2.0 Store protegido (frozen snapshots)
- `_snapshot = _captions.map(c => Object.freeze({...c}))` — reconstruído a cada mutação
- `Store.captions` getter retorna `_snapshot` (O(1), sem cópia)
- `_capByIdMut(id)` — referência mutável interna (uso exclusivo nas mutations)

### 2.1 Selection state
```js
_sel = { ids: new Set(), primaryId: null, anchorId: null, activePanel: null }
```

### 2.2 Comportamentos de clique
- Click simples: `selectOnly(id)` + seek vídeo
- Ctrl+Click: `toggleSelection(id)`
- Shift+Click: `selectRange(anchorId, id)`
- Ctrl+A: `selectAll()` (respeita painel ativo, não intercepta em campos de texto)
- Escape: fecha dropdown → depois `clearSelection()`

### 2.3 Classes CSS de seleção
- `.is-playing` — borda cinza (linha que toca, separada da seleção)
- `.is-selected` — borda laranja dim (#553300)
- `.is-primary` — borda laranja forte (var(--orange))

### 2.4 Batch bar
- Aparece só com 2+ itens selecionados
- `.hidden` quando 0 ou 1 item

### 2.5 Properties panel multi-select
- Campo texto desabilitado com mensagem
- Mixed values mostrados com `.mixed-badge`

### 2.6 Batch actions
- Aplicar estilo, toggle zoom/sfx/em, sliders size/pos/opacity, duplicar, deletar

### 2.7 Performance
- `_syncSelectionClasses()` — só alterna classes CSS, SEM re-render DOM
- `captionsBatchUpdated` — 1 emit para N mudanças

### 2.8 Acessibilidade
- `aria-selected`, `tabindex`, roles

### 2.9 Atalhos protegidos
- Ctrl+A só funciona fora de campos de texto

---

## NOVO SCRIPT COMPLETO (ETAPA 2)

O script abaixo substitui INTEIRAMENTE o `<script>` existente no arquivo `index.html`.

```javascript
// ═══════════════════════════════════════════════════════════════════
// VIRALUME STUDIO — ETAPA 2: STORE PROTEGIDO + MULTISSELEÇÃO + LOTE
// ═══════════════════════════════════════════════════════════════════

// ── ID Generator ──
let _idSeq = 0;
function generateId(prefix){return(prefix||'id')+'_'+Date.now().toString(36)+'_'+(++_idSeq).toString(36);}

// ── Centralized Store ──
const Store=(()=>{
  let _captions=[];
  let _snapshot=[]; // frozen shallow copies for external reads
  const _sel={ids:new Set(),primaryId:null,anchorId:null,activePanel:null};
  let _interaction=null; // Etapa 3 prep
  const _style={name:'Interativo 01',fontFamily:'Archivo',fontSize:20,fontWeight:800,letterSpacing:0.05,align:'center',posY:18,opacity:100,color:'#ffffff'};
  const _listeners={};
  let _version=0;

  // Events
  function on(event,fn){(_listeners[event]=_listeners[event]||[]).push(fn);}
  function emit(event,data){(_listeners[event]||[]).forEach(fn=>{try{fn(data);}catch(e){console.error('Store event',event,e);}});}

  // Internal mutable accessor
  function _capMut(id){return _captions.find(x=>x.id===id)||null;}
  function capIndexById(id){return _captions.findIndex(x=>x.id===id);}

  // Rebuild frozen snapshot (called after every mutation)
  function _rebuild(){_snapshot=_captions.map(c=>Object.freeze({...c}));}

  // Persist
  function _persist(){
    try{localStorage.setItem('vlm_caps',JSON.stringify(_captions));localStorage.setItem('vlm_style',JSON.stringify(_style));}catch(e){}
  }

  // ── Selection emit ──
  function _emitSel(origin){
    emit('selectionChanged',{
      id:_sel.primaryId,ids:[..._sel.ids],primaryId:_sel.primaryId,
      anchorId:_sel.anchorId,count:_sel.ids.size,activePanel:_sel.activePanel,origin
    });
  }

  // ── Caption mutations ──
  function setCaptions(arr){
    arr.forEach(c=>{if(!c.id)c.id=generateId('cap');});
    _captions=arr;_version++;_rebuild();_persist();
    emit('captionsReset',_snapshot);
  }
  function updateCaption(id,patch){
    const c=_capMut(id);if(!c)return null;
    Object.assign(c,patch);_version++;_rebuild();_persist();
    emit('captionUpdated',{id,patch,caption:Object.freeze({...c})});
    return Object.freeze({...c});
  }
  function addCaption(cap){
    if(!cap.id)cap.id=generateId('cap');
    _captions.push(cap);_version++;_rebuild();_persist();
    emit('captionsReset',_snapshot);
    return Object.freeze({...cap});
  }
  function deleteCaption(id){
    const idx=capIndexById(id);if(idx<0)return;
    _captions.splice(idx,1);
    _sel.ids.delete(id);
    if(_sel.primaryId===id){_sel.primaryId=_sel.ids.size>0?[..._sel.ids].pop():null;}
    if(_sel.anchorId===id)_sel.anchorId=null;
    _version++;_rebuild();_persist();
    _emitSel('delete');
    emit('captionsReset',_snapshot);
  }
  function duplicateCaption(id){
    const c=_capMut(id);if(!c)return null;
    const nc={...c,id:generateId('cap'),start:c.end,end:c.end+1.5};
    _captions.push(nc);_version++;_rebuild();_persist();
    emit('captionsReset',_snapshot);
    return Object.freeze({...nc});
  }

  // ── Batch mutations ──
  function batchUpdateCaptions(ids,patch){
    const valid=ids.filter(id=>_capMut(id)!==null);
    if(!valid.length)return[];
    valid.forEach(id=>{const c=_capMut(id);if(c)Object.assign(c,patch);});
    _version++;_rebuild();_persist();
    emit('captionsBatchUpdated',{ids:valid,changedFields:Object.keys(patch),patch,source:'batch',timestamp:Date.now()});
    return valid;
  }
  function deleteCaptions(ids){
    const del=new Set(ids.filter(id=>_capMut(id)!==null));
    if(!del.size)return;
    _captions=_captions.filter(c=>!del.has(c.id));
    del.forEach(id=>{_sel.ids.delete(id);});
    if(_sel.primaryId&&del.has(_sel.primaryId))_sel.primaryId=_sel.ids.size>0?[..._sel.ids].pop():null;
    if(_sel.anchorId&&del.has(_sel.anchorId))_sel.anchorId=null;
    _version++;_rebuild();_persist();
    _emitSel('deleteCaptions');
    emit('captionsReset',_snapshot);
  }
  function duplicateCaptions(ids){
    const toDup=ids.map(id=>_capMut(id)).filter(Boolean);
    const newIds=[];
    [...toDup].reverse().forEach(c=>{
      const nc={...c,id:generateId('cap'),start:c.end,end:c.end+1.5};
      const idx=capIndexById(c.id);
      _captions.splice(idx+1,0,nc);
      newIds.unshift(nc.id);
    });
    _version++;_rebuild();_persist();
    _sel.ids=new Set(newIds);_sel.primaryId=newIds[0]||null;_sel.anchorId=newIds[0]||null;
    _emitSel('duplicate');
    emit('captionsReset',_snapshot);
    return newIds;
  }

  // ── Interaction API (Etapa 3 prep) ──
  function beginInteraction(ids,field){
    _interaction={ids:[...ids],field,origValues:{}};
    ids.forEach(id=>{const c=_capMut(id);if(c)_interaction.origValues[id]=c[field];});
  }
  function previewBatchChange(patch){
    if(!_interaction)return;
    _interaction.ids.forEach(id=>{const c=_capMut(id);if(c)Object.assign(c,patch);});
    _rebuild();
    emit('captionsPreview',{ids:_interaction.ids,patch});
  }
  function commitInteraction(){
    if(!_interaction)return;
    _version++;_persist();
    emit('captionsBatchUpdated',{ids:_interaction.ids,changedFields:[_interaction.field],source:'interaction',timestamp:Date.now()});
    _interaction=null;
  }
  function cancelInteraction(){
    if(!_interaction)return;
    _interaction.ids.forEach(id=>{const c=_capMut(id);if(c&&_interaction.origValues[id]!==undefined)c[_interaction.field]=_interaction.origValues[id];});
    _rebuild();emit('captionsPreview',{ids:_interaction.ids,patch:{}});_interaction=null;
  }

  // ── Selection actions ──
  function selectOnly(id,origin){
    _sel.ids=id?new Set([id]):new Set();
    _sel.primaryId=id||null;_sel.anchorId=id||null;
    if(origin)_sel.activePanel=origin;
    _emitSel(origin);
  }
  function toggleSelection(id,origin){
    if(_sel.ids.has(id)){
      _sel.ids.delete(id);
      if(_sel.primaryId===id)_sel.primaryId=_sel.ids.size>0?[..._sel.ids].pop():null;
    }else{
      _sel.ids.add(id);_sel.primaryId=id;_sel.anchorId=id;
    }
    if(origin)_sel.activePanel=origin;
    _emitSel(origin);
  }
  function selectRange(anchorId,targetId,origin){
    const ai=capIndexById(anchorId),ti=capIndexById(targetId);
    if(ai<0||ti<0){selectOnly(targetId,origin);return;}
    const lo=Math.min(ai,ti),hi=Math.max(ai,ti);
    const rangeIds=_captions.slice(lo,hi+1).map(c=>c.id);
    _sel.ids=new Set(rangeIds);_sel.primaryId=targetId;
    if(origin)_sel.activePanel=origin;
    _emitSel(origin);
  }
  function selectAll(origin){
    _sel.ids=new Set(_captions.map(c=>c.id));
    _sel.primaryId=_captions.length?_captions[0].id:null;
    _sel.anchorId=_sel.primaryId;
    if(origin)_sel.activePanel=origin;
    _emitSel(origin);
  }
  function clearSelection(){
    _sel.ids=new Set();_sel.primaryId=null;_sel.anchorId=null;
    _emitSel('clear');
  }

  return{
    get captions(){return _snapshot;},
    capById(id){return _snapshot.find(c=>c.id===id)||null;},
    capIndexById,
    get style(){return _style;},
    get selection(){return{ids:[..._sel.ids],primaryId:_sel.primaryId,anchorId:_sel.anchorId,activePanel:_sel.activePanel};},
    get currentCapId(){return _sel.primaryId;},
    get currentCapIdx(){return capIndexById(_sel.primaryId);},
    get version(){return _version;},
    on,emit,
    setCaptions,updateCaption,addCaption,
    deleteCaption,removeCaptionById(id){return deleteCaption(id);},
    duplicateCaption,
    batchUpdateCaptions,deleteCaptions,duplicateCaptions,
    beginInteraction,previewBatchChange,commitInteraction,cancelInteraction,
    setCurrentCap(id){return selectOnly(id,null);},
    selectOnly,toggleSelection,selectRange,selectAll,clearSelection,
    isSelected(id){return _sel.ids.has(id);},
    getSelectedIds(){return[..._sel.ids];},
    getSelectedCaptions(){return _snapshot.filter(c=>_sel.ids.has(c.id));},
    setPrimarySelection(id){if(!_sel.ids.has(id))_sel.ids.add(id);_sel.primaryId=id;_emitSel('setPrimary');},
    _persist,
  };
})();

// ── Backward-compat global proxies ──
let currentFile=null;
let lastSFXTime={};
const HIGHLIGHT_COLORS=['#d44000','#3b82f6','#a78bfa','#22c55e','#f59e0b','#ec4899'];

Object.defineProperties(window,{
  captions:         {get(){return Store.captions;},      set(v){Store.setCaptions(v);},configurable:true},
  currentCapIdx:    {get(){return Store.currentCapIdx;}, set(v){const c=Store.captions[v];Store.setCurrentCap(c?c.id:null);},configurable:true},
  currentStyleName: {get(){return Store.style.name;},    set(v){Store.style.name=v;},configurable:true},
  capFontSize:      {get(){return Store.style.fontSize;}, set(v){Store.style.fontSize=v;},configurable:true},
  capPos:           {get(){return Store.style.posY;},    set(v){Store.style.posY=v;},configurable:true},
  capOpacity:       {get(){return Store.style.opacity;}, set(v){Store.style.opacity=v;},configurable:true},
  capColor:         {get(){return Store.style.color;},   set(v){Store.style.color=v;},configurable:true},
  capAlign:         {get(){return Store.style.align;},   set(v){Store.style.align=v;},configurable:true},
  capFont:          {get(){return Store.style.fontFamily;},set(v){Store.style.fontFamily=v;},configurable:true},
  capWeight:        {get(){return Store.style.fontWeight;},set(v){Store.style.fontWeight=v;},configurable:true},
  capSpacing:       {get(){return Store.style.letterSpacing;},set(v){Store.style.letterSpacing=v;},configurable:true},
  transcription:    {get(){return Store.captions.map(c=>({id:c.id,ts:c.start,text:c.text}));},set(){},configurable:true},
});

// ═══════════════════════════════════════════════════════════
// STYLE RENDERER
// ═══════════════════════════════════════════════════════════
function buildOverlayHTML(text,styleName){
  const s=Store.style;
  const fs=s.fontSize+'px',fw=s.fontWeight,ff=s.fontFamily,ls=s.letterSpacing+'em',al=s.align;
  const words=text.trim().split(/\s+/),h=Math.ceil(words.length/2);
  const A=words.slice(0,h).join(' '),B=words.slice(h).join(' ')||'';
  const base=`font:${fw} ${fs} ${ff};letter-spacing:${ls};text-shadow:0 2px 8px #000a,0 1px 2px #0008`;
  switch(styleName){
    case 'Interativo 01':
      return`<div style="${base};color:#fff;text-align:${al}">${A}</div>`+(B?`<div style="${base};color:#ffb347;background:#111;padding:2px 10px;border-radius:4px;margin-top:3px;text-align:${al};display:inline-block">${B}</div>`:'');
    case 'Interativo 02':
      return`<div style="${base};color:#fff;text-align:${al}">${A}</div>`+(B?`<div style="font:${fw} ${fs} ${ff};color:#fff;background:#d44000;padding:3px 12px;border-radius:4px;margin-top:3px;text-align:${al};display:inline-block;letter-spacing:${ls}">${B}</div>`:'');
    case 'Interativo 03':
      return`<div style="${base};color:#fff;text-align:${al}">${A}</div>`+(B?`<div style="font:${fw} ${fs} ${ff};color:#fff;border:2.5px solid #22c55e;padding:2px 10px;border-radius:4px;margin-top:3px;text-align:${al};display:inline-block;letter-spacing:${ls}">${B}</div>`:'');
    case 'Interativo 04':
      return`<div style="${base};color:#fff;text-align:${al}">${A}</div>`+(B?`<div style="${base};color:#22c55e;margin-top:3px;text-align:${al}">${B}</div>`:'');
    case 'Interativo 05':
      return`<div style="${base};color:#fff;text-align:${al}">${A}</div>`+(B?`<div style="font:${fw} ${fs} ${ff};color:#fff;background:#a855f7;padding:3px 12px;border-radius:4px;margin-top:3px;text-align:${al};display:inline-block;letter-spacing:${ls}">${B}</div>`:'');
    case 'Minimal 01':
      return`<div style="font:400 ${fs} ${ff};color:rgba(255,255,255,.88);letter-spacing:.06em;text-shadow:0 1px 4px #000;text-align:${al}">${text}</div>`;
    case 'Neon 01':
      return`<div style="font:${fw} ${fs} ${ff};color:#0ff;text-shadow:0 0 8px #0ff,0 0 20px #0ff;letter-spacing:${ls};text-align:${al}">${A}</div>`+(B?`<div style="font:${fw} ${fs} ${ff};color:#ff0;text-shadow:0 0 8px #ff0;letter-spacing:${ls};text-align:${al};margin-top:3px">${B}</div>`:'');
    case 'Karaokê 01':
      return`<div style="font:${fw} ${fs} ${ff};color:rgba(255,255,255,.4);letter-spacing:${ls};text-align:${al};text-shadow:0 1px 4px #000">${A}</div>`+(B?`<div style="font:${fw} ${fs} ${ff};color:#d44000;letter-spacing:${ls};text-align:${al};text-shadow:0 0 8px #d4400066;margin-top:3px">${B}</div>`:'');
    case 'Destaque 01':
      return`<div style="${base};color:#fff;text-transform:uppercase;letter-spacing:.12em;text-align:${al}">${A}</div>`+(B?`<div style="${base};color:#d44000;text-transform:uppercase;letter-spacing:.12em;text-align:${al};margin-top:3px">${B}</div>`:'');
    default:
      return`<div style="${base};color:${s.color};text-align:${al}">${text}</div>`;
  }
}

// ═══════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════
function toast(msg,type){
  const w=document.getElementById('toastWrap');
  const d=document.createElement('div');d.className='tst';
  d.style.borderColor=type==='ok'?'#1a4a1a':type==='err'?'#4a1a1a':'#2a2a2a';
  d.textContent=msg;w.appendChild(d);
  setTimeout(()=>d.style.opacity='0',3200);setTimeout(()=>d.remove(),3500);
}
function fmtS(s){if(!s||isNaN(s)||s<0)s=0;const m=Math.floor(s/60),sec=(s%60).toFixed(1);return m+':'+sec.toString().padStart(4,'0');}
function fmtTC(s){if(!s||isNaN(s)||s<0)s=0;const h=Math.floor(s/3600),m=Math.floor((s%3600)/60),sec=Math.floor(s%60),f=Math.round((s%1)*25);return String(h).padStart(2,'0')+':'+String(m).padStart(2,'0')+':'+String(sec).padStart(2,'0')+':'+String(f).padStart(2,'0');}

function playSFX(type){
  try{
    const ctx=new(window.AudioContext||window.webkitAudioContext)();
    const osc=ctx.createOscillator(),gain=ctx.createGain();
    osc.connect(gain);gain.connect(ctx.destination);
    if(type==='pop'||type==='click'){osc.frequency.setValueAtTime(900,ctx.currentTime);osc.frequency.exponentialRampToValueAtTime(200,ctx.currentTime+0.1);}
    else if(type==='whoosh'){osc.type='sawtooth';osc.frequency.setValueAtTime(300,ctx.currentTime);osc.frequency.exponentialRampToValueAtTime(1200,ctx.currentTime+0.2);}
    else if(type==='boom'){osc.frequency.setValueAtTime(120,ctx.currentTime);osc.frequency.exponentialRampToValueAtTime(40,ctx.currentTime+0.25);}
    else{osc.frequency.setValueAtTime(600,ctx.currentTime);}
    gain.gain.setValueAtTime(0.25,ctx.currentTime);gain.gain.exponentialRampToValueAtTime(0.001,ctx.currentTime+0.3);
    osc.start();osc.stop(ctx.currentTime+0.35);
  }catch(e){}
}

function renderOverlay(c){
  const ov=document.getElementById('capOverlay'),ow=document.getElementById('capOverlayWrap');
  if(!ov)return;
  if(!c){ov.innerHTML='';return;}
  ov.innerHTML=buildOverlayHTML(c.text,c.overlayStyle||Store.style.name);
  ov.style.opacity=Store.style.opacity/100;
  if(ow)ow.style.bottom=Store.style.posY+'%';
}
function refreshOverlay(){
  const v=document.getElementById('video');if(!v)return;
  const t=v.currentTime;
  const active=Store.captions.find(x=>t>=x.start&&t<x.end)||null;
  renderOverlay(active);
}

// ═══════════════════════════════════════════════════════════
// SELECTION SYNC — pure CSS class updates, no DOM rebuild
// ═══════════════════════════════════════════════════════════
function _syncSelectionClasses(){
  const sel=Store.selection;
  const primary=sel.primaryId;
  const selSet=new Set(sel.ids);
  document.querySelectorAll('[data-cap-id]').forEach(el=>{
    const id=el.dataset.capId;
    const isPrimary=id===primary;
    const isSelected=selSet.has(id);
    el.classList.toggle('is-primary',isPrimary);
    el.classList.toggle('is-selected',isSelected&&!isPrimary);
    el.setAttribute('aria-selected',(isSelected||isPrimary)?'true':'false');
  });
  document.querySelectorAll('.hl-card').forEach(card=>card.classList.toggle('active',card.dataset.capId===primary));
  document.querySelectorAll('.tl-block').forEach(b=>b.classList.toggle('active-block',b.dataset.capId===primary));
}

function _syncPropertiesPanel(){
  const sel=Store.selection;
  const count=sel.ids.length;
  const multiNote=document.getElementById('ppMultiNote');
  const ppText=document.getElementById('ppText');
  const ppNum=document.getElementById('ppCardNum');

  if(count===0){
    if(ppText&&ppText!==document.activeElement)ppText.value='';
    if(ppNum)ppNum.textContent='#--';
    if(multiNote)multiNote.style.display='none';
    if(ppText)ppText.classList.remove('pp-disabled-field');
    renderOverlay(null);
    return;
  }
  if(count===1){
    const c=Store.capById(sel.primaryId);if(!c)return;
    if(multiNote)multiNote.style.display='none';
    if(ppText)ppText.classList.remove('pp-disabled-field');
    if(ppText&&ppText!==document.activeElement)ppText.value=c.text;
    if(ppNum)ppNum.textContent='#'+String(Store.capIndexById(sel.primaryId)+1).padStart(2,'0');
    const ppSel=document.getElementById('ppStyleSel');if(ppSel)ppSel.value=c.overlayStyle||Store.style.name;
    updateCharCount();
    document.getElementById('chipZoom')?.classList.toggle('on',!!c.zoom);
    document.getElementById('chipSFX')?.classList.toggle('on',!!c.sfx);
    document.getElementById('chipEm')?.classList.toggle('on',c.style==='emphasis');
    document.getElementById('chipZoom')?.classList.remove('mixed');
    document.getElementById('chipSFX')?.classList.remove('mixed');
    document.getElementById('chipEm')?.classList.remove('mixed');
    const v=document.getElementById('video');
    if(v&&isFinite(c.start)&&v.paused)v.currentTime=c.start;
    renderOverlay(c);
  }else{
    if(multiNote)multiNote.style.display='block';
    if(ppText){ppText.classList.add('pp-disabled-field');ppText.value='Edição múltipla — use a barra de ações acima';}
    if(ppNum)ppNum.textContent='×'+count;
    _syncMultiChips();
  }
}

function _syncMultiChips(){
  const caps=Store.getSelectedCaptions();
  const zooms=new Set(caps.map(c=>!!c.zoom));
  const zChip=document.getElementById('chipZoom');
  if(zChip){zChip.classList.toggle('on',zooms.size===1&&[...zooms][0]===true);zChip.classList.toggle('mixed',zooms.size>1);}
  const sfxs=new Set(caps.map(c=>!!c.sfx));
  const sChip=document.getElementById('chipSFX');
  if(sChip){sChip.classList.toggle('on',sfxs.size===1&&[...sfxs][0]===true);sChip.classList.toggle('mixed',sfxs.size>1);}
  const ems=new Set(caps.map(c=>c.style==='emphasis'));
  const eChip=document.getElementById('chipEm');
  if(eChip){eChip.classList.toggle('on',ems.size===1&&[...ems][0]===true);eChip.classList.toggle('mixed',ems.size>1);}
}

Store.on('selectionChanged',()=>{
  _syncSelectionClasses();
  _syncPropertiesPanel();
  updateBatchBar();
  const primary=Store.selection.primaryId;
  if(primary)document.getElementById('trLine_'+primary)?.scrollIntoView({block:'nearest',behavior:'smooth'});
});

// ═══════════════════════════════════════════════════════════
// captionUpdated — surgical DOM updates
// ═══════════════════════════════════════════════════════════
Store.on('captionUpdated',({id,patch})=>{
  const c=Store.capById(id);if(!c)return;
  if('text'in patch){
    const line=document.getElementById('trLine_'+id);
    if(line){const td=line.querySelector('.tr-text');if(td)_buildTrWords(td,c);}
    const hlText=document.querySelector('.hl-card[data-cap-id="'+id+'"] .hl-text');
    if(hlText)hlText.textContent=c.text;
    const tlBlock=document.querySelector('.tl-block[data-cap-id="'+id+'"]');
    if(tlBlock){const w=parseFloat(tlBlock.style.width);if(w>30)tlBlock.textContent=c.text.substring(0,Math.floor(w/7));}
    if(id===Store.currentCapId){refreshOverlay();const pp=document.getElementById('ppText');if(pp&&pp!==document.activeElement)pp.value=c.text;updateCharCount();}
    _updateTrStats();
  }
  if('hi'in patch||'zoom'in patch||'sfx'in patch||'style'in patch||'overlayStyle'in patch){
    renderHighlights();updateTL();
    if('hi'in patch)updateCounts();
    if(id===Store.currentCapId){_syncSelectionClasses();_syncPropertiesPanel();}
  }
});

Store.on('captionsBatchUpdated',({ids,changedFields,patch})=>{
  const structural=changedFields.some(f=>['hi','start','end'].includes(f));
  if(structural){renderHighlights();updateTL();updateCounts();}
  else{
    ids.forEach(id=>{
      const c=Store.capById(id);if(!c)return;
      _refreshHLChips(id);
      const b=document.querySelector('.tl-block[data-cap-id="'+id+'"]');
      if(b)b.style.background=c.style==='emphasis'?'#3a1200':'#1e1e1e';
    });
    if(patch&&'overlayStyle'in patch)refreshOverlay();
  }
  updateBatchBar();
  _syncPropertiesPanel();
  _syncSelectionClasses();
});

Store.on('captionsReset',()=>{
  renderTranscription();renderHighlights();updateTL();updateCounts();
});

Store.on('captionsPreview',({ids})=>{
  if(ids.includes(Store.selection.primaryId))refreshOverlay();
});

// ═══════════════════════════════════════════════════════════
// UI TABS / MODE
// ═══════════════════════════════════════════════════════════
function setMainTab(el){document.querySelectorAll('.main-tab').forEach(t=>t.classList.remove('active'));el.classList.add('active');}
function setMode(mode,el){
  document.querySelectorAll('.mode-pill').forEach(p=>p.classList.remove('active'));el.classList.add('active');
  const tc=document.getElementById('transcriptionCol'),hl=document.getElementById('highlightsCol'),rc=document.getElementById('rcHL');
  if(mode==='cartoes'){if(tc)tc.style.display='none';if(rc)rc.style.display='none';if(hl){hl.style.flex='1';hl.style.width='';}}
  else if(mode==='transcricao'){if(hl)hl.style.display='none';if(rc)rc.style.display='none';if(tc)tc.style.flex='1';}
  else{if(tc){tc.style.display='';tc.style.flex='1';}if(hl){hl.style.display='';hl.style.flex='';hl.style.width='290px';}if(rc)rc.style.display='';}
}
function toggleLP(){document.getElementById('leftPanel')?.classList.toggle('collapsed');}
function filterStyle(cat,el){
  document.querySelectorAll('.sf').forEach(s=>s.classList.remove('active'));el.classList.add('active');
  document.querySelectorAll('.style-card').forEach(c=>{c.style.display=(cat==='todos'||c.dataset.cat===cat)?'':'none';});
}
function selectStyle(el,name){
  document.querySelectorAll('.style-card').forEach(c=>c.classList.remove('active'));el.classList.add('active');
  Store.style.name=name;
  const ppSel=document.getElementById('ppStyleSel');if(ppSel)ppSel.value=name;
  if(Store.currentCapId)Store.updateCaption(Store.currentCapId,{overlayStyle:name});
  refreshOverlay();toast('Estilo "'+name+'" ativo','ok');
}
function setPPTab(btn,id){
  document.querySelectorAll('.pp-tab').forEach(t=>t.classList.remove('active'));btn.classList.add('active');
  ['ppBasic','ppStyle','ppAnim'].forEach(t=>{const el=document.getElementById(t);if(el)el.style.display=t===id?'block':'none';});
}
function setAlign(a,btn){
  Store.style.align=a;
  ['alignLeft','alignCenter','alignRight'].forEach(bid=>{const b=document.getElementById(bid);if(b){b.style.borderColor='var(--line)';b.style.color='#333';}});
  btn.style.borderColor='var(--orange)';btn.style.color='var(--orange)';refreshOverlay();
}

// ═══════════════════════════════════════════════════════════
// PROPERTIES PANEL
// ═══════════════════════════════════════════════════════════
function updateCharCount(){const ta=document.getElementById('ppText'),cc=document.getElementById('ppCharCount');if(ta&&cc)cc.textContent=ta.value.length+'/120';}

document.getElementById('ppText')?.addEventListener('input',function(){
  updateCharCount();
  const sel=Store.selection;
  if(sel.ids.length===1&&Store.currentCapId)Store.updateCaption(Store.currentCapId,{text:this.value});
});
document.getElementById('ppStyleSel')?.addEventListener('change',function(){
  Store.style.name=this.value;
  if(Store.selection.ids.length===1&&Store.currentCapId)Store.updateCaption(Store.currentCapId,{overlayStyle:this.value});
  else if(Store.selection.ids.length>1)Store.batchUpdateCaptions(Store.getSelectedIds(),{overlayStyle:this.value});
  document.querySelectorAll('.style-card').forEach(sc=>sc.classList.toggle('active',sc.dataset.style===this.value));
  refreshOverlay();
});
document.getElementById('ppSizeSlider')?.addEventListener('input',function(){
  Store.style.fontSize=parseInt(this.value);
  document.getElementById('ppSizeVal').textContent=Store.style.fontSize+'px';refreshOverlay();
});
document.getElementById('ppPosSlider')?.addEventListener('input',function(){
  Store.style.posY=parseInt(this.value);
  document.getElementById('ppPosVal').textContent=Store.style.posY+'%';
  const ow=document.getElementById('capOverlayWrap');if(ow)ow.style.bottom=Store.style.posY+'%';
});
document.getElementById('ppOpSlider')?.addEventListener('input',function(){
  Store.style.opacity=parseInt(this.value);
  document.getElementById('ppOpVal').textContent=Store.style.opacity+'%';
  const ov=document.getElementById('capOverlay');if(ov)ov.style.opacity=Store.style.opacity/100;
});
document.getElementById('ppColorText')?.addEventListener('input',function(){Store.style.color=this.value;refreshOverlay();});
document.getElementById('ppFont')?.addEventListener('change',function(){Store.style.fontFamily=this.value;refreshOverlay();});
document.getElementById('ppWeightSlider')?.addEventListener('input',function(){
  Store.style.fontWeight=parseInt(this.value);
  document.getElementById('ppWeightVal').textContent=Store.style.fontWeight;refreshOverlay();
});
document.getElementById('ppSpacingSlider')?.addEventListener('input',function(){
  Store.style.letterSpacing=this.value/100;
  document.getElementById('ppSpacingVal').textContent=Store.style.letterSpacing.toFixed(2)+'em';refreshOverlay();
});

function _handleChipClick(prop){
  const sel=Store.selection;
  if(sel.ids.length===0)return;
  if(sel.ids.length===1&&Store.currentCapId){
    const c=Store.capById(Store.currentCapId);if(!c)return;
    const patch={};
    if(prop==='zoom')patch.zoom=!c.zoom;
    else if(prop==='sfx')patch.sfx=c.sfx?null:'pop';
    else if(prop==='em')patch.style=c.style==='emphasis'?'standard':'emphasis';
    Store.updateCaption(Store.currentCapId,patch);
    if(patch.sfx)playSFX(patch.sfx);
    _refreshHLChips(Store.currentCapId);
  }else{
    batchToggle(prop);
  }
}

document.getElementById('chipZoom')?.addEventListener('click',()=>_handleChipClick('zoom'));
document.getElementById('chipSFX')?.addEventListener('click',()=>_handleChipClick('sfx'));
document.getElementById('chipEm')?.addEventListener('click',()=>_handleChipClick('em'));

document.getElementById('btnApplyAll')?.addEventListener('click',()=>{
  const updated=Store.captions.map(c=>({...c,overlayStyle:Store.style.name}));
  Store.setCaptions(updated);
  refreshOverlay();toast('Estilo "'+Store.style.name+'" aplicado a '+Store.captions.length+' cartões','ok');
});

// ═══════════════════════════════════════════════════════════
// TRANSCRIPTION
// ═══════════════════════════════════════════════════════════
function _buildTrWords(textDiv,c){
  textDiv.innerHTML='';
  c.text.split(' ').forEach(w=>{
    const sp=document.createElement('span');sp.className='word';sp.textContent=w+' ';sp.dataset.capId=c.id;
    sp.ondblclick=e=>{
      e.stopPropagation();sp.contentEditable='true';sp.classList.add('highlighted');sp.focus();
      try{const r=document.createRange();r.selectNodeContents(sp);const s=window.getSelection();s.removeAllRanges();s.addRange(r);}catch(e2){}
      const origW=w;
      sp.onblur=()=>{
        sp.contentEditable='false';sp.classList.remove('highlighted');
        const newText=Array.from(textDiv.querySelectorAll('.word')).map(s=>s.textContent.trim()).filter(Boolean).join(' ');
        if(newText!==c.text)Store.updateCaption(c.id,{text:newText});
      };
      sp.onkeydown=e2=>{if(e2.key==='Enter'){e2.preventDefault();sp.blur();}if(e2.key==='Escape'){sp.textContent=origW+' ';sp.blur();}};
    };
    sp.onclick=e=>{e.stopPropagation();if(sp.contentEditable==='true')return;};
    textDiv.appendChild(sp);
  });
}

function renderTranscription(){
  const body=document.getElementById('transcriptionBody');if(!body)return;
  body.innerHTML='';
  const sel=Store.selection;
  Store.captions.forEach(c=>{
    const line=document.createElement('div');
    line.className='tr-line';line.id='trLine_'+c.id;
    line.dataset.capId=c.id;
    line.setAttribute('role','option');line.setAttribute('tabindex','0');
    const isPrimary=c.id===sel.primaryId;
    const isSelected=sel.ids.includes(c.id);
    line.classList.toggle('is-primary',isPrimary);
    line.classList.toggle('is-selected',isSelected&&!isPrimary);
    line.setAttribute('aria-selected',(isPrimary||isSelected)?'true':'false');
    if(isPrimary)line.classList.add('active');
    const ts=document.createElement('div');ts.className='tr-ts';ts.textContent=fmtS(c.start);
    const textDiv=document.createElement('div');textDiv.className='tr-text';
    _buildTrWords(textDiv,c);
    line.appendChild(ts);line.appendChild(textDiv);
    line.onclick=e=>{
      if(e.target.classList.contains('word')||e.target.contentEditable==='true')return;
      const isCtrl=e.ctrlKey||e.metaKey,isShift=e.shiftKey;
      if(isCtrl){Store.toggleSelection(c.id,'transcription');}
      else if(isShift){const anc=Store.selection.anchorId;if(anc)Store.selectRange(anc,c.id,'transcription');else Store.selectOnly(c.id,'transcription');}
      else{const v=document.getElementById('video');if(v&&isFinite(c.start))v.currentTime=c.start;Store.selectOnly(c.id,'transcription');}
    };
    line.onkeydown=e=>{
      if(e.code==='Space'||e.code==='Enter'){e.preventDefault();const v=document.getElementById('video');if(v&&isFinite(c.start))v.currentTime=c.start;Store.selectOnly(c.id,'transcription');}
    };
    body.appendChild(line);
  });
  _updateTrStats();
}

function _updateTrStats(){
  let tw=0,tc2=0;
  Store.captions.forEach(c=>{tw+=c.text.split(/\s+/).filter(Boolean).length;tc2+=c.text.length;});
  const ts=document.getElementById('trStats');if(ts)ts.textContent=tw+' palavras · '+tc2+' caracteres';
  const sw=document.getElementById('sbWords');if(sw)sw.textContent='Palavras: '+tw;
  const sc=document.getElementById('sbChars');if(sc)sc.textContent='Caracteres: '+tc2;
}

// ═══════════════════════════════════════════════════════════
// HIGHLIGHTS
// ═══════════════════════════════════════════════════════════
function _refreshHLChips(id){
  const card=document.querySelector('.hl-card[data-cap-id="'+id+'"]');if(!card)return;
  const c=Store.capById(id);if(!c)return;
  card.querySelectorAll('.hlchip').forEach(chip=>{
    if(chip.classList.contains('hlc-z'))chip.classList.toggle('on',!!c.zoom);
    if(chip.classList.contains('hlc-s'))chip.classList.toggle('on',!!c.sfx);
    if(chip.classList.contains('hlc-e'))chip.classList.toggle('on',c.style==='emphasis');
  });
}

function renderHighlights(){
  const list=document.getElementById('hlList');if(!list)return;list.innerHTML='';
  const hls=Store.captions.filter(c=>c.hi);
  const hlCount=document.getElementById('hlCount');if(hlCount)hlCount.textContent=hls.length;
  const sel=Store.selection;
  hls.forEach((c,idx)=>{
    const color=HIGHLIGHT_COLORS[idx%HIGHLIGHT_COLORS.length];
    const card=document.createElement('div');
    card.className='hl-card';card.dataset.capId=c.id;
    card.setAttribute('role','option');card.setAttribute('tabindex','0');
    const isPrimary=c.id===sel.primaryId;
    const isSelected=sel.ids.includes(c.id);
    card.classList.toggle('is-primary',isPrimary);
    card.classList.toggle('is-selected',isSelected&&!isPrimary);
    if(isPrimary)card.classList.add('active');
    card.setAttribute('aria-selected',(isPrimary||isSelected)?'true':'false');
    card.innerHTML=`<div class="hl-time"><span class="hl-time-val">${fmtS(c.start)} — ${fmtS(c.end)}</span><div class="hl-card-actions"><button class="hca" onclick="event.stopPropagation();Store.selectOnly('${c.id}','highlights')">✏</button><button class="hca" onclick="event.stopPropagation();Store.duplicateCaption('${c.id}');toast('Duplicado','ok')">⧉</button><button class="hca" onclick="event.stopPropagation();removeHL('${c.id}')">🗑</button></div></div><div class="hl-body"><div class="hl-text" style="color:${color}">${c.text}</div><div class="hl-chips"><span class="hlchip hlc-z ${c.zoom?'on':''}" onclick="toggleCapProp('${c.id}','zoom')">Z</span><span class="hlchip hlc-s ${c.sfx?'on':''}" onclick="toggleCapProp('${c.id}','sfx')">SFX</span><span class="hlchip hlc-e ${c.style==='emphasis'?'on':''}" onclick="toggleCapProp('${c.id}','em')">EM</span></div></div>`;
    card.onclick=e=>{
      if(e.target.closest('.hca')||e.target.closest('.hlchip'))return;
      const isCtrl=e.ctrlKey||e.metaKey,isShift=e.shiftKey;
      if(isCtrl){Store.toggleSelection(c.id,'highlights');}
      else if(isShift){const anc=Store.selection.anchorId;if(anc)Store.selectRange(anc,c.id,'highlights');else Store.selectOnly(c.id,'highlights');}
      else{const v=document.getElementById('video');if(v&&isFinite(c.start))v.currentTime=c.start;Store.selectOnly(c.id,'highlights');}
    };
    list.appendChild(card);
  });
}

function toggleCapProp(id,prop){
  const c=Store.capById(id);if(!c)return;
  const patch={};
  if(prop==='zoom')patch.zoom=!c.zoom;
  else if(prop==='sfx')patch.sfx=c.sfx?null:'pop';
  else if(prop==='em')patch.style=c.style==='emphasis'?'standard':'emphasis';
  Store.updateCaption(id,patch);
  if(patch.sfx)playSFX(patch.sfx);
}
function removeHL(id){Store.updateCaption(id,{hi:false});}
function duplicateCap(id){Store.duplicateCaption(id);toast('Cartão duplicado','ok');}
function addHighlight(){
  const caps=Store.captions,last=caps[caps.length-1];
  Store.addCaption({start:last?last.end:0,end:last?last.end+2:2,text:'NOVO DESTAQUE',style:'emphasis',zoom:true,sfx:null,hi:true,overlayStyle:Store.style.name});
  toast('Destaque adicionado','ok');
}

// ═══════════════════════════════════════════════════════════
// TIMELINE
// ═══════════════════════════════════════════════════════════
function updateTL(){
  const laneC=document.getElementById('tlLaneCaption'),laneH=document.getElementById('tlLaneHL'),ruler=document.getElementById('tlRuler');
  if(!laneC)return;
  const caps=Store.captions,total=caps.length?Math.max(caps[caps.length-1]?.end||1,1):10;
  const W=laneC.offsetWidth||800;
  laneC.querySelectorAll('.tl-block').forEach(e=>e.remove());
  laneH.querySelectorAll('.tl-block').forEach(e=>e.remove());
  ruler.querySelectorAll('.tl-tick').forEach(e=>e.remove());
  const step=Math.max(1,Math.round(total/10));
  for(let s=0;s<=total;s+=step){const t=document.createElement('div');t.className='tl-tick';t.style.left=((s/total)*W)+'px';t.textContent=fmtS(s);ruler.appendChild(t);}
  const sel=Store.selection;
  caps.forEach(c=>{
    const x=(c.start/total)*W,w=Math.max(4,((c.end-c.start)/total)*W);
    const isPrimary=c.id===sel.primaryId;
    const isSelected=sel.ids.includes(c.id);
    const b=document.createElement('div');
    b.className='tl-block';b.dataset.capId=c.id;
    b.classList.toggle('is-primary',isPrimary);
    b.classList.toggle('is-selected',isSelected&&!isPrimary);
    b.classList.toggle('active-block',isPrimary);
    b.setAttribute('aria-selected',(isPrimary||isSelected)?'true':'false');
    b.style.cssText=`left:${x}px;width:${w}px;background:${c.style==='emphasis'?'#3a1200':'#1e1e1e'};height:20px`;
    if(w>30)b.textContent=c.text.substring(0,Math.floor(w/7));b.title=c.text;
    b.onclick=e=>{
      const isCtrl=e.ctrlKey||e.metaKey,isShift=e.shiftKey;
      if(isCtrl){Store.toggleSelection(c.id,'timeline');}
      else if(isShift){const anc=Store.selection.anchorId;if(anc)Store.selectRange(anc,c.id,'timeline');else Store.selectOnly(c.id,'timeline');}
      else{const v=document.getElementById('video');if(v&&isFinite(c.start))v.currentTime=c.start;Store.selectOnly(c.id,'timeline');}
    };
    laneC.appendChild(b);
  });
  caps.filter(c=>c.hi).forEach((c,idx)=>{
    const x=(c.start/total)*W,w=Math.max(4,((c.end-c.start)/total)*W),col=HIGHLIGHT_COLORS[idx%HIGHLIGHT_COLORS.length];
    const b=document.createElement('div');b.className='tl-block';b.dataset.capId=c.id;
    b.style.cssText=`left:${x}px;width:${w}px;background:${col};height:20px`;
    if(w>30)b.textContent=c.text.substring(0,Math.floor(w/7));b.title=c.text;
    b.onclick=e=>{
      if(e.ctrlKey||e.metaKey){Store.toggleSelection(c.id,'timeline');}
      else{const v=document.getElementById('video');if(v&&isFinite(c.start))v.currentTime=c.start;Store.selectOnly(c.id,'timeline');}
    };
    laneH.appendChild(b);
  });
  const vs=document.getElementById('tlVideoStrip'),as2=document.getElementById('tlAudioStrip');
  if(vs&&currentFile){vs.style.display='flex';vs.textContent=currentFile.name;}
  if(as2&&currentFile)as2.style.display='block';
  const dm=Math.floor(total/60),ds=Math.floor(total%60);
  const sb=document.getElementById('sbDuration');
  if(sb)sb.textContent='Duração total: '+String(dm).padStart(2,'0')+':'+String(ds).padStart(2,'0');
}

function updateCounts(){
  const n=Store.captions.length;
  const s1=document.getElementById('sbCardCount');if(s1)s1.textContent=n+' cartões';
  const s2=document.getElementById('sbCartoes');if(s2)s2.textContent=n+' cartões';
  const hc=document.getElementById('hlCount');if(hc)hc.textContent=Store.captions.filter(c=>c.hi).length;
}

// ═══════════════════════════════════════════════════════════
// BATCH BAR
// ═══════════════════════════════════════════════════════════
function updateBatchBar(){
  const sel=Store.selection;
  const count=sel.ids.length;
  const bar=document.getElementById('batchBar');if(!bar)return;
  if(count>=2){
    bar.classList.remove('hidden');
    document.getElementById('batchCount').textContent=count+' itens selecionados';
    _updateBatchBtnStates();
  }else{bar.classList.add('hidden');closeBatchStyleDrop();}
}

function _updateBatchBtnStates(){
  const caps=Store.getSelectedCaptions();
  const allZ=caps.every(c=>!!c.zoom),noneZ=caps.every(c=>!c.zoom);
  const zB=document.getElementById('batchZoom');
  if(zB){zB.classList.toggle('active',allZ);zB.classList.toggle('mixed',!allZ&&!noneZ);}
  const allS=caps.every(c=>!!c.sfx),noneS=caps.every(c=>!c.sfx);
  const sB=document.getElementById('batchSFX');
  if(sB){sB.classList.toggle('active',allS);sB.classList.toggle('mixed',!allS&&!noneS);}
  const allE=caps.every(c=>c.style==='emphasis'),noneE=caps.every(c=>c.style!=='emphasis');
  const eB=document.getElementById('batchEm');
  if(eB){eB.classList.toggle('active',allE);eB.classList.toggle('mixed',!allE&&!noneE);}
}

function batchToggle(field){
  const ids=Store.getSelectedIds(),caps=Store.getSelectedCaptions();
  let patch;
  if(field==='zoom'){const allOn=caps.every(c=>!!c.zoom);patch={zoom:!allOn};}
  else if(field==='sfx'){const allOn=caps.every(c=>!!c.sfx);patch={sfx:allOn?null:'pop'};}
  else if(field==='em'){const allOn=caps.every(c=>c.style==='emphasis');patch={style:allOn?'standard':'emphasis'};}
  if(patch)Store.batchUpdateCaptions(ids,patch);
}

function batchApplyStyle(styleName){
  Store.batchUpdateCaptions(Store.getSelectedIds(),{overlayStyle:styleName});
  closeBatchStyleDrop();
  refreshOverlay();
  toast('Estilo "'+styleName+'" aplicado','ok');
}

function batchRemoveEffects(){
  Store.batchUpdateCaptions(Store.getSelectedIds(),{zoom:false,sfx:null,style:'standard'});
  toast('Efeitos removidos','ok');
}

function batchDuplicate(){
  const ids=Store.getSelectedIds();
  Store.duplicateCaptions(ids);
  toast(ids.length+' itens duplicados','ok');
}

function batchDelete(){
  const ids=Store.getSelectedIds(),count=ids.length;
  showConfirmModal(
    'Excluir '+count+' cartão'+(count>1?'s':'')+' selecionado'+(count>1?'s':'')+'?',
    'Esta ação poderá ser desfeita quando o histórico estiver disponível (Etapa 3).',
    ()=>{Store.deleteCaptions(ids);toast(count+' cartões excluídos','ok');}
  );
}

function toggleBatchStyleDrop(e){e&&e.stopPropagation();document.getElementById('batchStyleDrop')?.classList.toggle('open');}
function closeBatchStyleDrop(){document.getElementById('batchStyleDrop')?.classList.remove('open');}

(function initBatchSliders(){
  function onInput(field,val){Store.style[field]=val;refreshOverlay();}
  function onUp(){Store._persist();}
  const bSize=document.getElementById('batchSize');
  if(bSize){
    bSize.addEventListener('input',function(){onInput('fontSize',parseInt(this.value));document.getElementById('ppSizeVal').textContent=Store.style.fontSize+'px';});
    bSize.addEventListener('change',onUp);
  }
  const bPos=document.getElementById('batchPos');
  if(bPos){
    bPos.addEventListener('input',function(){onInput('posY',parseInt(this.value));const ow=document.getElementById('capOverlayWrap');if(ow)ow.style.bottom=Store.style.posY+'%';document.getElementById('ppPosVal').textContent=Store.style.posY+'%';});
    bPos.addEventListener('change',onUp);
  }
  const bOp=document.getElementById('batchOp');
  if(bOp){
    bOp.addEventListener('input',function(){onInput('opacity',parseInt(this.value));const ov=document.getElementById('capOverlay');if(ov)ov.style.opacity=Store.style.opacity/100;document.getElementById('ppOpVal').textContent=Store.style.opacity+'%';});
    bOp.addEventListener('change',onUp);
  }
})();

document.addEventListener('click',e=>{
  if(!e.target.closest('#batchStyleBtn')&&!e.target.closest('#batchStyleDrop'))closeBatchStyleDrop();
});

// ═══════════════════════════════════════════════════════════
// CONFIRM MODAL
// ═══════════════════════════════════════════════════════════
function showConfirmModal(title,msg,onConfirm){
  const overlay=document.getElementById('confirmModal');
  if(!overlay){onConfirm();return;}
  document.getElementById('confirmTitle').textContent=title;
  document.getElementById('confirmMsg').textContent=msg;
  overlay.classList.add('open');
  const okBtn=document.getElementById('confirmOk');
  const cancelBtn=document.getElementById('confirmCancel');
  const cleanup=()=>{overlay.classList.remove('open');okBtn.onclick=null;cancelBtn.onclick=null;};
  okBtn.onclick=()=>{cleanup();onConfirm();};
  cancelBtn.onclick=cleanup;
}

// ═══════════════════════════════════════════════════════════
// VIDEO PLAYER
// ═══════════════════════════════════════════════════════════
function loadVideoFile(f){
  currentFile=f;
  const video=document.getElementById('video');
  video.src=URL.createObjectURL(f);video.style.display='block';
  document.getElementById('pvEmpty').style.display='none';
  document.getElementById('projectName').textContent=f.name.replace(/\.[^.]+$/,'');
  updateTL();updateCounts();
}

(function initPlayer(){
  const video=document.getElementById('video'),fill=document.getElementById('pvFill'),clock=document.getElementById('pvClock'),ph=document.getElementById('tlPlayhead'),phr=document.getElementById('tlPhRuler'),tc=document.getElementById('tlTC');
  document.getElementById('videoFile')?.addEventListener('change',function(){const f=this.files[0];if(!f)return;loadVideoFile(f);});
  const phone=document.getElementById('pvPhone');
  if(phone){
    phone.addEventListener('dragover',e=>{e.preventDefault();phone.classList.add('drag-over');});
    phone.addEventListener('dragleave',()=>phone.classList.remove('drag-over'));
    phone.addEventListener('drop',e=>{e.preventDefault();phone.classList.remove('drag-over');const f=e.dataTransfer.files[0];if(f&&f.type.startsWith('video/'))loadVideoFile(f);else toast('Arraste um arquivo de vídeo válido','err');});
  }
  document.addEventListener('dragover',e=>e.preventDefault());
  document.addEventListener('drop',e=>{e.preventDefault();const f=e.dataTransfer.files[0];if(f&&f.type.startsWith('video/'))loadVideoFile(f);});

  video?.addEventListener('timeupdate',()=>{
    const t=video.currentTime,d=video.duration||0;
    if(fill&&d>0)fill.style.width=((t/d)*100)+'%';
    if(clock)clock.textContent=fmtS(t)+' / '+fmtS(d);
    if(tc)tc.textContent=fmtTC(t);
    const caps=Store.captions,total=caps.length?Math.max(caps[caps.length-1]?.end||1,1):(d||10);
    const W=document.getElementById('tlLaneCaption')?.offsetWidth||800;
    const frac=total>0?Math.min(t/total,1):0;
    if(ph)ph.style.left=(frac*W)+'px';
    if(phr)phr.style.left=(frac*(document.getElementById('tlRuler')?.offsetWidth||800))+'px';
    const ov=document.getElementById('capOverlay');
    const activeIdx=caps.findIndex(c=>t>=c.start&&t<c.end);
    if(ov){
      if(activeIdx>=0){
        const c=caps[activeIdx];
        if(c.sfx&&Math.abs(t-c.start)<0.12){const key=c.start+'_'+c.sfx;if(!lastSFXTime[key]){lastSFXTime[key]=true;playSFX(c.sfx);}}
        renderOverlay(c);
      }else ov.innerHTML='';
    }
    if(Math.round(t)%5===0)lastSFXTime={};
    caps.forEach((c,i)=>{
      const next=caps[i+1];
      const isPlaying=t>=c.start&&(!next||t<next.start);
      const el=document.getElementById('trLine_'+c.id);
      if(el){
        if(isPlaying&&!el.classList.contains('is-playing')){el.classList.add('is-playing');if(!Store.isSelected(c.id))el.scrollIntoView({block:'nearest',behavior:'smooth'});}
        else if(!isPlaying)el.classList.remove('is-playing');
      }
    });
  });
  video?.addEventListener('loadedmetadata',()=>{
    const d=video.duration;
    if(clock)clock.textContent='0:00.0 / '+fmtS(d);
    if(!Store.captions.length){const dm=Math.floor(d/60),ds=Math.floor(d%60);document.getElementById('sbDuration').textContent='Duração total: '+String(dm).padStart(2,'0')+':'+String(ds).padStart(2,'0');}
    updateTL();toast('Vídeo carregado — '+fmtS(d),'ok');
  });
  video?.addEventListener('ended',()=>{const b=document.getElementById('btnPlay');if(b)b.textContent='▶ PLAY';});
  document.getElementById('pvProgress')?.addEventListener('click',function(e){if(!video||!video.duration)return;video.currentTime=(e.offsetX/this.offsetWidth)*video.duration;});
  document.getElementById('tlLaneCaption')?.addEventListener('click',function(e){
    if(e.target.classList.contains('tl-block'))return;
    if(!video||!video.duration)return;
    const caps=Store.captions,total=caps.length?caps[caps.length-1].end:video.duration;
    video.currentTime=(e.offsetX/this.offsetWidth)*total;
  });
  document.getElementById('speedSel')?.addEventListener('change',function(){if(video)video.playbackRate=parseFloat(this.value);});
})();

function togglePlay(){const v=document.getElementById('video'),b=document.getElementById('btnPlay');if(!v)return;if(v.paused){v.play();if(b)b.textContent='⏸ PAUSE';}else{v.pause();if(b)b.textContent='▶ PLAY';}}
function seekStart(){const v=document.getElementById('video');if(v)v.currentTime=0;}
function seekEnd(){const v=document.getElementById('video');if(v&&v.duration)v.currentTime=v.duration;}
function seekFrame(dir){const v=document.getElementById('video');if(v)v.currentTime=Math.max(0,v.currentTime+dir*(1/25));}

// ═══════════════════════════════════════════════════════════
// KEYBOARD SHORTCUTS
// ═══════════════════════════════════════════════════════════
document.addEventListener('keydown',e=>{
  const tag=e.target.tagName;
  const editable=tag==='TEXTAREA'||tag==='INPUT'||tag==='SELECT'||e.target.contentEditable==='true';
  if(editable&&!(e.ctrlKey||e.metaKey))return;

  if(document.getElementById('confirmModal')?.classList.contains('open')){
    if(e.code==='Escape'){document.getElementById('confirmModal').classList.remove('open');}
    return;
  }

  if(e.code==='Space'&&!editable){e.preventDefault();togglePlay();return;}
  if(e.code==='ArrowLeft'&&!editable){e.preventDefault();seekFrame(-1);return;}
  if(e.code==='ArrowRight'&&!editable){e.preventDefault();seekFrame(1);return;}
  if(e.code==='Home'&&!editable){e.preventDefault();seekStart();return;}
  if(e.code==='End'&&!editable){e.preventDefault();seekEnd();return;}
  if((e.ctrlKey||e.metaKey)&&e.code==='KeyF'){e.preventDefault();document.getElementById('trSearch')?.focus();return;}

  if((e.ctrlKey||e.metaKey)&&e.code==='KeyA'&&!editable){
    e.preventDefault();
    Store.selectAll(Store.selection.activePanel||'transcription');
    return;
  }

  if(e.code==='Escape'){
    const bDrop=document.getElementById('batchStyleDrop');
    if(bDrop&&bDrop.classList.contains('open')){closeBatchStyleDrop();return;}
    Store.clearSelection();
    return;
  }

  if((e.ctrlKey||e.metaKey)&&e.code==='KeyZ'&&!e.shiftKey){e.preventDefault();toast('Undo — disponível na Etapa 3','info');return;}
  if((e.ctrlKey||e.metaKey)&&(e.code==='KeyY'||(e.shiftKey&&e.code==='KeyZ'))){e.preventDefault();toast('Redo — disponível na Etapa 3','info');return;}
});

// ═══════════════════════════════════════════════════════════
// SEARCH
// ═══════════════════════════════════════════════════════════
document.getElementById('trSearch')?.addEventListener('input',function(){
  const q=this.value.toLowerCase().trim();
  document.querySelectorAll('.tr-line').forEach(line=>{
    if(!q){line.style.display='';return;}
    const text=line.querySelector('.tr-text')?.textContent.toLowerCase()||'';
    line.style.display=text.includes(q)?'':'none';
  });
});

// ═══════════════════════════════════════════════════════════
// API
// ═══════════════════════════════════════════════════════════
document.getElementById('btnTranscribe')?.addEventListener('click',async function(){
  if(!currentFile){toast('Carregue um vídeo primeiro','err');return;}
  const orig=this.textContent;this.textContent='⏳ Transcrevendo...';this.disabled=true;
  toast('Transcrevendo com IA... pode levar alguns minutos','info');
  try{
    const r=await fetch('/api/transcribe',{method:'POST',headers:{'Content-Length':currentFile.size,'X-File-Name':currentFile.name},body:currentFile});
    const d=await r.json();if(!d.ok)throw new Error(d.erro);
    Store.setCaptions(d.captions.map(c=>({...c,hi:c.highlight||c.text_style==='emphasis'||c.style==='emphasis',overlayStyle:Store.style.name})));
    if(Store.captions.length>0)Store.selectOnly(Store.captions[0].id,'transcription');
    toast(Store.captions.length+' cartões transcritos','ok');
  }catch(e){toast('Erro: '+e.message,'err');}
  finally{this.textContent=orig;this.disabled=false;}
});

document.getElementById('btnImportSRT')?.addEventListener('click',()=>{
  const inp=document.createElement('input');inp.type='file';inp.accept='.srt';
  inp.onchange=function(){
    const f=this.files[0];if(!f)return;
    const rd=new FileReader();rd.onload=e=>{
      const lines=e.target.result.split(/\n/),parsed=[];let i=0;
      while(i<lines.length){
        if(/^\d+$/.test(lines[i]?.trim())){i++;
          const tm=lines[i]?.match(/(\d+:\d+:\d+[,.]\d+)\s*-->\s*(\d+:\d+:\d+[,.]\d+)/);
          if(tm){
            const ts=s=>{const[h,m,r]=s.split(':');return parseInt(h)*3600+parseInt(m)*60+parseFloat(r.replace(',','.'));};
            const start=ts(tm[1]),end=ts(tm[2]);i++;
            const tl=[];while(i<lines.length&&lines[i].trim()!==''){tl.push(lines[i].trim());i++;}
            parsed.push({start,end,text:tl.join(' ').toUpperCase(),style:'standard',zoom:false,sfx:null,hi:false,overlayStyle:Store.style.name});
          }
        }else i++;
      }
      if(parsed.length){Store.setCaptions(parsed);if(Store.captions.length>0)Store.selectOnly(Store.captions[0].id,'transcription');toast(parsed.length+' legendas importadas','ok');}
      else toast('SRT inválido ou vazio','err');
    };rd.readAsText(f);
  };inp.click();
});

document.getElementById('btnExportSRT')?.addEventListener('click',()=>{
  if(!Store.captions.length){toast('Nenhuma legenda para exportar','err');return;}
  const rows=Store.captions.map((c,i)=>{
    const f=s=>{const h=Math.floor(s/3600),m=Math.floor((s%3600)/60),sec=s%60;return String(h).padStart(2,'0')+':'+String(m).padStart(2,'0')+':'+String(Math.floor(sec)).padStart(2,'0')+','+String(Math.round((sec%1)*1000)).padStart(3,'0');};
    return (i+1)+'\n'+f(c.start)+' --> '+f(c.end)+'\n'+c.text;
  }).join('\n\n');
  const name=currentFile?currentFile.name.replace(/\.[^.]+$/,''):'viralume';
  const a=document.createElement('a');a.href='data:text/srt;charset=utf-8,'+encodeURIComponent(rows);a.download=name+'.srt';a.click();
  toast('SRT exportado: '+name+'.srt','ok');
});

document.getElementById('btnRender')?.addEventListener('click',async function(){
  if(!currentFile){toast('Carregue um vídeo primeiro','err');return;}
  if(!Store.captions.length){toast('Transcreva ou importe legendas primeiro','err');return;}
  const orig=this.textContent;this.disabled=true;this.textContent='⏳ Exportando...';
  toast('Renderizando vídeo com legendas... aguarde','info');
  try{
    const r=await fetch('/api/render',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({video:{name:currentFile.name},captions:Store.captions,effects:{style:Store.style.name,fontSize:Store.style.fontSize,posY:Store.style.posY,opacity:Store.style.opacity}})});
    const d=await r.json();if(!d.ok)throw new Error(d.erro);
    toast('Exportado: '+d.arquivo,'ok');
  }catch(e){toast('Erro na exportação: '+e.message,'err');}
  finally{this.disabled=false;this.textContent=orig;}
});

document.getElementById('btnDivide')?.addEventListener('click',()=>{
  if(!Store.captions.length){toast('Nenhuma legenda carregada','err');return;}
  let changed=0;const newCaps=[];
  Store.captions.forEach(c=>{
    const words=c.text.split(' ');
    if(words.length>5){
      const mid=Math.ceil(words.length/2),dur=(c.end-c.start)/2;
      newCaps.push({...c,text:words.slice(0,mid).join(' '),end:c.start+dur});
      newCaps.push({...c,id:generateId('cap'),text:words.slice(mid).join(' '),start:c.start+dur});
      changed++;
    }else newCaps.push(c);
  });
  if(!changed){toast('Nenhum cartão longo para dividir','info');return;}
  Store.setCaptions(newCaps);
  toast(changed+' cartões divididos — total: '+Store.captions.length,'ok');
});

document.getElementById('btnUndo')?.addEventListener('click',()=>toast('Undo — disponível na Etapa 3','info'));
document.getElementById('btnRedo')?.addEventListener('click',()=>toast('Redo — disponível na Etapa 3','info'));

// ═══════════════════════════════════════════════════════════
// RESIZE HANDLES
// ═══════════════════════════════════════════════════════════
function colResize(hid,lid,minW){
  const h=document.getElementById(hid);if(!h)return;
  h.addEventListener('mousedown',e=>{
    const left=document.getElementById(lid);if(!left)return;
    const startX=e.clientX,startW=left.offsetWidth;
    document.body.style.cursor='col-resize';document.body.style.userSelect='none';
    function mv(ev){left.style.width=Math.max(minW||80,startW+ev.clientX-startX)+'px';left.style.flex='none';}
    function up(){document.body.style.cursor='';document.body.style.userSelect='';document.removeEventListener('mousemove',mv);document.removeEventListener('mouseup',up);}
    document.addEventListener('mousemove',mv);document.addEventListener('mouseup',up);
  });
}
function colResizeRight(hid,rid,minW){
  const h=document.getElementById(hid);if(!h)return;
  h.addEventListener('mousedown',e=>{
    const right=document.getElementById(rid);if(!right)return;
    const startX=e.clientX,startW=right.offsetWidth;
    document.body.style.cursor='col-resize';document.body.style.userSelect='none';
    function mv(ev){right.style.width=Math.max(minW||180,startW-(ev.clientX-startX))+'px';}
    function up(){document.body.style.cursor='';document.body.style.userSelect='';document.removeEventListener('mousemove',mv);document.removeEventListener('mouseup',up);}
    document.addEventListener('mousemove',mv);document.addEventListener('mouseup',up);
  });
}
colResize('rcLP','leftPanel',120);
colResize('rcHL','transcriptionCol',200);
colResize('rcProps','highlightsCol',160);
colResizeRight('rcPV','previewCol',200);
(function initTLResize(){
  const h=document.getElementById('rrTL'),tl=document.getElementById('timelineWrap');if(!h||!tl)return;
  h.addEventListener('mousedown',e=>{
    const startY=e.clientY,startH=tl.offsetHeight;
    document.body.style.cursor='row-resize';document.body.style.userSelect='none';
    function mv(ev){tl.style.height=Math.max(80,Math.min(320,startH-(ev.clientY-startY)))+'px';}
    function up(){document.body.style.cursor='';document.body.style.userSelect='';document.removeEventListener('mousemove',mv);document.removeEventListener('mouseup',up);}
    document.addEventListener('mousemove',mv);document.addEventListener('mouseup',up);
  });
})();

// ═══════════════════════════════════════════════════════════
// INIT — restore persisted state
// ═══════════════════════════════════════════════════════════
(function loadPersisted(){
  try{
    const sStyle=localStorage.getItem('vlm_style');
    if(sStyle)Object.assign(Store.style,JSON.parse(sStyle));
    const sCaps=localStorage.getItem('vlm_caps');
    if(sCaps){
      const caps=JSON.parse(sCaps);
      caps.forEach(c=>{if(!c.id)c.id=generateId('cap');});
      Store.setCaptions(caps);
      const badge=document.getElementById('savedBadge');
      if(badge){badge.textContent='Sessão restaurada';setTimeout(()=>{badge.textContent='Salvo';},3000);}
      return;
    }
  }catch(e){console.warn('loadPersisted',e);}
  renderTranscription();renderHighlights();updateTL();updateCounts();
})();
```

---

## COMO APLICAR O SCRIPT

### Método PowerShell (caminho D:\CORTE VIRAL\studio\index.html):

```powershell
# 1. Ler o arquivo atual
$file = "D:\CORTE VIRAL\studio\index.html"
$content = [System.IO.File]::ReadAllText($file, [System.Text.Encoding]::UTF8)

# 2. Encontrar posições do script
$scriptStart = $content.IndexOf("<script>")
$scriptEnd = $content.IndexOf("</script>") + "</script>".Length
$afterScript = $content.Substring($scriptEnd)  # deve ser: </body>\r\n</html>

# 3. Ler o novo script do arquivo de contexto (copie o bloco JS acima para um .js separado)
$newScript = [System.IO.File]::ReadAllText("D:\CORTE VIRAL\studio\etapa2_script.js", [System.Text.Encoding]::UTF8)

# 4. Montar e escrever
$newContent = $content.Substring(0, $scriptStart) + "<script>`n" + $newScript + "`n</script>`n" + $afterScript
[System.IO.File]::WriteAllText($file, $newContent, [System.Text.Encoding]::UTF8)
```

**Importante**: Salve o bloco JS acima como `D:\CORTE VIRAL\studio\etapa2_script.js` (SEM as marcações de código markdown), depois rode o PowerShell acima.

---

## PRÓXIMAS ETAPAS (PENDENTES)

### Etapa 4 — Autosave híbrido
- IndexedDB para snapshots locais
- Backend debounce 800–1500ms
- Versão com timestamp, conflito detection

### Etapa 5 — Painéis redimensionáveis + 5 presets de workspace

---

## CSS JÁ INJETADO NO HTML (Etapa 2)

```css
/* Selection states */
.tr-line.is-selected{background:#0d0800!important;border-left:2px solid #553300}
.tr-line.is-primary{background:#130a00!important;border-left:2px solid var(--orange)}
.tr-line.is-primary .tr-ts{color:var(--orange)}
.tr-line.is-playing{border-left:2px solid #333}
.hl-card.is-selected{border-color:#553300!important;background:#0a0400}
.hl-card.is-primary{border-color:var(--orange)!important;background:#110600}
.tl-block.is-selected{outline:1px solid #553300;outline-offset:1px}
.tl-block.is-primary{outline:2px solid var(--orange);outline-offset:1px}

/* Batch bar */
.batch-bar{display:flex;align-items:center;gap:6px;background:#0e0800;border-top:1px solid #3a1500;border-bottom:1px solid #3a1500;padding:0 12px;height:42px;flex-shrink:0}
.batch-bar.hidden{height:0;padding:0;border:none;overflow:hidden;pointer-events:none;opacity:0}
.batch-btn.active{background:var(--orange);color:#fff}
.batch-btn.mixed{border-style:dashed;background:#1e0e00;color:#cc6600}
.batch-style-drop{position:absolute;bottom:calc(100%+5px);display:none;flex-direction:column}
.batch-style-drop.open{display:flex}

/* Confirm modal */
.confirm-overlay{position:fixed;inset:0;background:#000b;z-index:9990;display:none;align-items:center;justify-content:center}
.confirm-overlay.open{display:flex}

/* Multi-select PP */
.pp-multi-note{font:400 11px Archivo;color:#553300;font-style:italic}
.mixed-badge{font:500 8px Archivo;color:#553300;background:#1a0800;border:1px dashed #3a1500}
```

## HTML JÁ INJETADO (Etapa 2)

- `<div id="ppMultiNote" class="pp-multi-note" style="display:none">` — dentro de `#ppBasic`
- Batch bar com id `batchBar` — antes de `<!-- TIMELINE -->`
- Confirm modal `<div class="confirm-overlay" id="confirmModal">` — antes de `</div><!-- /app -->`
