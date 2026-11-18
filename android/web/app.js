'use strict';
if(!Element.prototype.replaceChildren)Element.prototype.replaceChildren=function(...nodes){while(this.firstChild)this.removeChild(this.firstChild);for(const item of nodes)this.appendChild(item instanceof Node?item:document.createTextNode(String(item)));};
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="app-token"]').content;
let destination = {uri:'',path:'Downloads',pending:false}, destinationTimer;
let prefs = {}, current = null, query = '', page = 1, busy = false, downloading = false;
let selected = new Set(), returning = 'home', playing = null, playSequence = 0;
let showJob = false, jobPolling = false, settingsQueue = Promise.resolve(), toastTimer;
let playbackQueue = [], queueIndex = -1, shuffle = false, repeatMode = 'off';
let searchType = 'tracks', searchResults = null;
const icons = {
  play:'<svg viewBox="0 0 24 24"><path d="m9 5 11 7-11 7z"/></svg>',
  download:'<svg viewBox="0 0 24 24"><path d="M12 3v12m-5-5 5 5 5-5M5 17v4h14v-4"/></svg>'
};
async function api(path, body, controller = new AbortController()) {
  const timer = setTimeout(() => controller.abort(), 65000);
  try {
    const response = await fetch('/api/' + path, {
      method: body === undefined ? 'GET' : 'POST',
      headers: {'X-App-Token':token, 'Content-Type':'application/json'},
      body: body === undefined ? undefined : JSON.stringify(body), signal:controller.signal
    });
    const data = await response.json();
    if (!response.ok || data.error) throw new Error(data.error || 'Please try again.');
    return data;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('Request timed out. Please try again.');
    throw error;
  } finally { clearTimeout(timer); }
}
function toast(text) {
  clearTimeout(toastTimer); $('toast').textContent = text; $('toast').hidden = false;
  toastTimer = setTimeout(() => $('toast').hidden = true, 5500);
}
function navigate(name) { if (location.hash === '#' + name) renderScreen(); else location.hash = name; }
function renderScreen() {
  const name = location.hash.slice(1);
  const active = name === 'settings' ? 'settings' : name === 'details' && current ? 'details' : 'home';
  for (const id of ['home','details','settings']) $(id).hidden = id !== active;
  window.scrollTo(0,0);
}
window.addEventListener('hashchange', renderScreen);
document.querySelectorAll('[data-open-settings]').forEach(button => button.addEventListener('click', () => {
  returning = !$('details').hidden ? 'details' : 'home'; navigate('settings');
}));
$('settings-back').onclick = () => navigate(returning);
$('details-back').onclick = () => {
  if(searchResults && ['song','album'].includes(current.kind)) {
    current=searchResults;searchResults=null;selected.clear();renderCollection();message('');window.scrollTo(0,0);
  } else navigate('home');
};
function message(text) { $('home-status').textContent = text; $('detail-status').textContent = text; }
function setBusy(value) { busy = value; $('archive').disabled = value; $('archive').textContent = value ? 'Loading…' : 'Archive'; $('query').disabled = value; $('paste').disabled = value; document.querySelectorAll('[data-search-type], [data-open-album]').forEach(b=>b.disabled=value); }
function renderSearchType(){
  document.querySelectorAll('[data-search-type]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.searchType===searchType)));
  $('search-hint').textContent=searchType==='albums'?'Search albums, then open one to view its songs. Links open directly.':'Search for tracks, or paste a song, album or playlist link.';
}
document.querySelectorAll('[data-search-type]').forEach(button=>button.onclick=()=>{
  if(busy || searchType===button.dataset.searchType)return;
  searchType=button.dataset.searchType;renderSearchType();
  if(!$('home').hidden) scheduleSuggestions();
  else if(!$('details').hidden && current && ['search','album-search'].includes(current.kind)){$('query').value=query;archive();}
});
function duration(seconds) { const n = Math.max(0,Number(seconds)||0); return Math.floor(n/60) + ':' + String(Math.floor(n%60)).padStart(2,'0'); }
function node(tag, className, text) { const n = document.createElement(tag); if(className) n.className = className; if(text !== undefined) n.textContent = text; return n; }
function art(url, title) {
  const img = node('img','art'); img.alt = title ? 'Cover: ' + title : 'Cover art'; img.loading = 'lazy';
  const fallback = 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100" fill="#2b1a25"/><text x="50" y="65" text-anchor="middle" fill="#ff6b91" font-size="50">♪</text></svg>');
  img.src = typeof url === 'string' && url.startsWith('https://') ? url : fallback;
  img.onerror = () => { img.onerror = null; img.src = fallback; }; return img;
}
function qualityNote() { $('quality-note').textContent = 'M4A / AAC · ' + (prefs.quality || '320') + ' kbps requested · Preview before downloading'; }
let suggestionTimer, suggestionRequest, suggestionVersion = 0;

function clearSuggestions() {
  suggestionVersion++;
  clearTimeout(suggestionTimer);
  if(suggestionRequest) suggestionRequest.abort();
  $('instant-results').hidden = true;
  $('instant-list').replaceChildren();
  $('home').classList.remove('typing');
}
function scheduleSuggestions() {
  clearSuggestions();
  const term = $('query').value.trim();
  if(!term || term.includes('://') || /^www\./i.test(term) || busy) return;
  const version = suggestionVersion;
  $('home').classList.add('typing');
  $('instant-results').hidden = false;
  $('instant-status').textContent = 'Searching…';
  suggestionTimer = setTimeout(async () => {
    suggestionRequest = new AbortController();
    try {
      const data = await api('archive', {query:term, search_type:searchType, suggest:true}, suggestionRequest);
      if(version !== suggestionVersion) return;
      const items = data.albums || data.suggestions || [];
      $('instant-status').textContent = items.length ? (data.albums ? 'Albums' : 'Tracks') : 'No results found.';
      for(const item of items) {
        const row = node('button','suggestion');
        row.type = 'button';
        const copy = node('span','suggestion-copy');
        copy.append(node('strong','',item.title),node('span','',item.artist));
        row.append(art(item.image,item.title),copy);
        row.onclick = () => { $('query').blur(); archive(1,item.url); };
        $('instant-list').append(row);
      }
    } catch(error) {
      if(version === suggestionVersion) $('instant-status').textContent = error.message;
    }
  }, 300);
}
$('query').addEventListener('input',scheduleSuggestions);
$('query').addEventListener('keydown',event=>{if(event.key==='Escape')clearSuggestions();});

async function archive(nextPage=1, chosenUrl='') {
  if (busy) return;
  const value = chosenUrl || $('query').value.trim();
  if(!chosenUrl) clearSuggestions();
  if (!value) { message('Enter a song name, artist or link.'); $('query').focus(); return; }
  setBusy(true); message(searchType==='albums'?'Finding albums…':'Finding tracks…');
  try {
    const info = await api('archive', {query:value,page:nextPage,search_type:searchType});
    current = info; query = value; page = nextPage;searchResults=null;
    selected = new Set(['search','album-search'].includes(info.kind) ? [] : info.songs.map(s => s.key));
    renderCollection(); navigate('details'); message(info.note || ((info.kind==='album-search'?info.albums:info.songs).length ? '' : info.kind==='album-search'?'No albums found. Try a different name.':'No tracks found. Try a different name.'));
  } catch(error) { message(error.message); toast(error.message); }
  finally { setBusy(false); }
}
$('archive-form').onsubmit = event => { event.preventDefault(); archive(); };
$('paste').onclick = async () => {
  try {
    let text = '';
    try { if(navigator.clipboard) text = await navigator.clipboard.readText(); } catch (_) {}
    if(!text) text = (await api('clipboard',{})).text;
    if(!text) throw new Error('Clipboard is empty.');
    $('query').value = text.trim(); scheduleSuggestions(); $('query').focus(); message('Link pasted. Tap Archive to see details.');
  } catch(error) { toast(error.message); }
};
async function openAlbum(album){
  if(busy)return;
  const results=current;setBusy(true);message('Opening album…');
  try{
    const info=await api('archive',{query:album.url});
    if(info.kind!=='album')throw new Error('This result is not an album. Please search again.');
    searchResults=results;current=info;selected=new Set(info.songs.map(s=>s.key));
    renderCollection();message('');window.scrollTo(0,0);
  }catch(error){message(error.message);toast(error.message);}
  finally{setBusy(false);}
}
function renderCollection() {
  const albumSearch=current.kind==='album-search', search = current.kind === 'search' || albumSearch, single = current.kind === 'song';
  const items=albumSearch?current.albums:current.songs;
  $('details-heading').textContent = albumSearch?'Album results':search ? 'Search results' : single ? 'Song details' : current.kind === 'album' ? 'Album details' : 'Playlist details';
  $('details-back').setAttribute('aria-label',searchResults?'Back to search results':'Back to home');
  $('result-modes').hidden=!search;renderSearchType();
  $('details').classList.toggle('single-detail',single);
  const container = $('collection'); container.replaceChildren();
  if (!search) container.append(art(current.image, current.title));
  const info = node('div','collection-info');
  info.append(node('span','eyebrow',search ? 'Find your next favourite' : current.kind));
  info.append(node('h2','',current.title));
  if(current.artist) info.append(node('p','',current.artist));
  const total = current.songs.reduce((sum,s) => sum + s.duration,0);
  info.append(node('p','',[current.year, items.length + (albumSearch?(items.length===1?' album':' albums'):(items.length === 1 ? ' song' : ' songs')), !search && total ? duration(total) : ''].filter(Boolean).join(' · ')));
  if(single && current.songs.length) {
    const song = current.songs[0];
    info.append(node('p','track-context',[song.album,song.language].filter(Boolean).join(' · ')));
    const play = node('button','secondary detail-play','▶  Play track');
    play.onclick = () => startPlayback(song);
    info.append(play);
  }
  container.append(info);
  $('collection-playback').hidden = !['album','playlist'].includes(current.kind) || !current.songs.length;
  $('selection-tools').hidden = search || single;
  $('download-selected').hidden = search;
  $('download-album-zip').hidden=current.kind!=='album';
  $('download-album-zip').disabled=downloading || !current.songs.length;
  $('quality-note').hidden=albumSearch;
  $('tracks').hidden=albumSearch || single;$('albums').hidden=!albumSearch;$('albums').replaceChildren();
  if(albumSearch)for(const album of current.albums){
    const card=node('button','album-card');card.type='button';card.dataset.openAlbum='true';
    card.setAttribute('aria-label','Open album '+album.title);card.append(art(album.image,album.title));
    const text=node('div','album-info');text.append(node('h3','',album.title));
    if(album.artist)text.append(node('p','',album.artist));
    text.append(node('p','',album.year||'Album'));
    if(album.matched_song)text.append(node('p','album-match','Includes: '+album.matched_song));
    card.append(text,node('span','album-arrow','›'));
    card.onclick=()=>openAlbum(album);$('albums').append(card);
  }
  $('tracks').replaceChildren();
  for(const song of current.songs) {
    if(current.kind === 'search') {
      const row = node('button','track suggestion');
      row.type = 'button';
      const copy = node('span','suggestion-copy');
      copy.append(node('strong','',song.title),node('span','',song.artist));
      row.append(art(song.image,song.title),copy);
      row.onclick = () => {
        searchResults = current;
        current = {kind:'song', title:song.title, artist:song.artist, year:song.year, image:song.image, songs:[song]};
        selected = new Set([song.key]);
        renderCollection();
        window.scrollTo(0,0);
      };
      $('tracks').append(row);
      continue;
    }
    const row = node('article','track'); row.dataset.key = song.key;
    if(!search && !single) {
      const check = node('input','track-check'); check.type='checkbox'; check.checked=selected.has(song.key);
      check.setAttribute('aria-label','Select ' + song.title);
      check.onchange=()=>{if(check.checked)selected.add(song.key);else selected.delete(song.key);selectionState();}; row.append(check);
    }
    row.append(art(song.image,song.title));
    const text=node('div','track-info'); text.append(node('h3','',song.title));
    text.append(node('p','',song.artist || 'Artist unavailable'));
    text.append(node('p','',[duration(song.duration),song.language,song.year].filter(Boolean).join(' · ')));
    if(search && song.album) text.append(node('p','',song.album));
    row.append(text);
    const actions=node('div','track-actions');
    const play=node('button','icon-button'); play.innerHTML=icons.play; play.setAttribute('aria-label','Play ' + song.title); play.onclick=()=>startPlayback(song);
    const download=node('button','icon-button'); download.innerHTML=icons.download; download.setAttribute('aria-label','Download ' + song.title); download.dataset.download='true'; download.disabled=downloading; download.onclick=()=>startDownload([song.key],false);
    actions.append(play,download);row.append(actions);$('tracks').append(row);
  }
  $('pagination').hidden=!search;
  $('previous').disabled=page<=1; $('next').disabled=typeof current.has_more==='boolean'?!current.has_more:items.length<20;
  $('page-number').textContent='Page ' + page;
  qualityNote(); selectionState();
}
function selectionState() {
  $('selected-count').textContent=selected.size+' selected';
  $('download-selected').textContent=current && current.kind==='song' ? 'Download song' : 'Download selected ('+selected.size+')';
  $('download-selected').disabled=downloading || !selected.size;
}
$('select-all').onclick=()=>{selected=new Set(current.songs.map(s=>s.key));renderCollection();};
$('select-none').onclick=()=>{selected.clear();renderCollection();};
$('download-selected').onclick=()=>startDownload([...selected],true);
$('download-album-zip').onclick=()=>startDownload(current.songs.map(s=>s.key),true,true);
$('previous').onclick=()=>{if(!busy){$('query').value=query;archive(page-1);}};
$('next').onclick=()=>{if(!busy){$('query').value=query;archive(page+1);}};
async function startDownload(keys,bundle,forceZip=false) {
  if(downloading) return toast('A download is already running.');
  if(!keys.length) return toast('Select at least one song.');
  downloading=true; disableDownloads();
  try {showJob=true;renderJob(await api('download',{keys,bundle,...(forceZip?{format:'zip'}:{})}));$('job').scrollIntoView({block:'nearest',behavior:'smooth'});}
  catch(error){downloading=false;disableDownloads();toast(error.message);}
}
function disableDownloads(){document.querySelectorAll('[data-download]').forEach(b=>b.disabled=downloading);selectionState();renderDestination();}
function renderJob(job){
  if(job.active)showJob=true;
  downloading=!!job.active;disableDownloads();
  $('job').hidden=!showJob;
  $('job-message').textContent=job.message || 'Ready.';
  $('progress').value=job.progress || 0;
  $('cancel').hidden=!job.active;$('dismiss-job').hidden=!!job.active;
  $('job-detail').textContent=[job.active ? job.detail : '', job.destination].filter(Boolean).join(' · ');
  const errors=[...(job.errors || []),...(job.warnings || [])];
  $('job-errors').hidden=!errors.length;
  $('error-list').replaceChildren(...errors.map(text=>node('p','error-line',text)));
}
$('cancel').onclick=async()=>{try{await api('cancel',{});$('job-message').textContent='Cancelling…';}catch(e){toast(e.message);}};
$('dismiss-job').onclick=()=>{showJob=false;$('job').hidden=true;};
async function poll(){if(jobPolling)return;jobPolling=true;try{renderJob(await api('job'));}catch(_){}finally{jobPolling=false;}}
function renderFilenamePreviews(){
  const samples={title:'Track title',artist:'Artist',albumArtist:'Album artist',album:'Album title',year:'2026',track:'03',disc:'2',id:'SongID',language:'Hindi'};
  document.querySelectorAll('[data-preview]').forEach(label=>{
    const key=label.dataset.preview, control=document.querySelector('[data-setting="'+key+'"]');
    let text=(control.value||'').replace(/\{([A-Za-z]+)\}/g,(whole,key)=>samples[key]||whole);
    text=text.replace(/[<>:"/\\|?*]/g,'_').replace(/\.(m4a|aac|zip)$/i,'');
    label.textContent=text+(key==='album_zip_template'?'.zip':'.m4a');
  });
}
function renderDestination(){
  $('destination-path').value=destination.uri?destination.path:'Downloads/'+(prefs.folder||'JS-DL');
  $('choose-folder').disabled=downloading||destination.pending;
  $('default-folder').disabled=downloading||destination.pending||!destination.uri;
  $('reset').disabled=downloading||destination.pending;
  $('folder').disabled=!!destination.uri;
  $('destination-status').textContent=destination.error||(destination.pending?'Choose a folder in the Android picker…':destination.uri?'Custom location saved. Album and disc folders are created inside it.':'Choose a folder on your phone or SD card. Your choice is remembered.');
}
async function loadDestination(){try{destination=await api('destination');renderDestination();}catch(error){$('destination-status').textContent=error.message;}}
$('choose-folder').onclick=async()=>{
  try{destination=await api('folder/pick',{});renderDestination();clearInterval(destinationTimer);destinationTimer=setInterval(async()=>{await loadDestination();if(!destination.pending)clearInterval(destinationTimer);},900);}
  catch(error){toast(error.message);}
};
$('default-folder').onclick=async()=>{try{destination=await api('folder/default',{});renderDestination();}catch(error){toast(error.message);}};
function populateSettings(){
  document.querySelectorAll('[data-setting]').forEach(control=>{const v=prefs[control.dataset.setting];if(control.type==='checkbox')control.checked=!!v;else control.value=v || '';});
  $('player-quality').value=prefs.quality || '320';qualityNote();renderFilenamePreviews();renderDestination();
}
function saveSetting(key,value){
  $('settings-status').textContent='Saving…';
  settingsQueue=settingsQueue.catch(()=>{}).then(async()=>{
    try {
      prefs=await api('settings',{patch:{[key]:value}});
      $('settings-status').textContent='Changes save automatically.';renderFilenamePreviews();renderDestination();
      if(key==='quality'){
        document.querySelector('[data-setting="quality"]').value=prefs.quality;
        $('player-quality').value=prefs.quality;qualityNote();
        if(playing)await playSong(playing,true);
      }
    }catch(error){$('settings-status').textContent=error.message;populateSettings();toast(error.message);}
  });return settingsQueue;
}
document.querySelectorAll('[data-setting]').forEach(control=>{
  control.onchange=()=>saveSetting(control.dataset.setting,control.type==='checkbox'?control.checked:control.value);
  if(control.dataset.setting.endsWith('_template'))control.addEventListener('input',renderFilenamePreviews);
});
$('reset').onclick=()=>{
  settingsQueue=settingsQueue.catch(()=>{}).then(async()=>{
    try{const was=prefs.quality;prefs=await api('settings',{reset:true});if(destination.uri)destination=await api('folder/default',{});populateSettings();$('settings-status').textContent='Default settings restored.';toast('Defaults restored.');if(playing&&was!==prefs.quality)await playSong(playing,true);}
    catch(error){toast(error.message);}
  });
};
function shuffled(songs){
  const result=songs.slice();
  for(let i=result.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[result[i],result[j]]=[result[j],result[i]];}
  return result;
}
function renderQueue(){
  $('queue-position').textContent=playbackQueue.length ? (queueIndex+1)+' / '+playbackQueue.length : '';
  $('player-previous').disabled=queueIndex<0 || (repeatMode!=='all' && queueIndex===0);
  $('player-next').disabled=queueIndex<0 || (repeatMode!=='all' && queueIndex>=playbackQueue.length-1);
  $('player-shuffle').setAttribute('aria-pressed',String(shuffle));
}
function startPlayback(song, mix=false){
  // Copy this collection so browsing another album cannot change the active queue.
  const source=current && ['album','playlist'].includes(current.kind)?current.songs:[song];
  source.forEach((item,index)=>item.queueOrder=index);
  shuffle=mix;
  playbackQueue=mix?shuffled(source):source.slice();
  queueIndex=mix?0:playbackQueue.findIndex(item=>item.key===song.key);
  if(queueIndex<0){playbackQueue=[song];queueIndex=0;}
  renderQueue();return playSong(playbackQueue[queueIndex]);
}
function moveQueue(offset){
  if(!playbackQueue.length)return;
  let next=queueIndex+offset;
  if(repeatMode==='all')next=(next+playbackQueue.length)%playbackQueue.length;
  if(next<0 || next>=playbackQueue.length)return;
  queueIndex=next;renderQueue();return playSong(playbackQueue[queueIndex],false,true);
}
$('play-all').onclick=()=>startPlayback(current.songs[0]);
$('shuffle-all').onclick=()=>startPlayback(current.songs[0],true);
$('player-previous').onclick=()=>moveQueue(-1);
$('player-next').onclick=()=>moveQueue(1);
$('player-shuffle').onclick=()=>{
  if(!playing)return;
  shuffle=!shuffle;
  const rest=playbackQueue.filter(s=>s.key!==playing.key);
  playbackQueue=[playing,...(shuffle?shuffled(rest):rest.sort((a,b)=>a.queueOrder-b.queueOrder))];
  queueIndex=0;renderQueue();
};
$('player-repeat').onclick=()=>{
  repeatMode = {off:'all', all:'one', one:'off'}[repeatMode];
  const control = $('player-repeat');
  control.dataset.mode = repeatMode;
  control.setAttribute('aria-label','Repeat '+repeatMode);
  control.title = 'Repeat '+repeatMode;
  $('audio').loop=repeatMode==='one';
  renderQueue();
};
$('audio').onended=()=>{
  if(!playing || !playbackQueue.length)return;
  if(repeatMode==='one'){
    const audio=$('audio');audio.currentTime=0;
    audio.play().catch(()=>{$('player-status').textContent='Tap play to repeat this song.';});
  }else if(queueIndex<playbackQueue.length-1 || repeatMode==='all')moveQueue(1);
  else $('player-status').textContent='Playback finished.';
};
const media = $('audio');
function syncTransport() {
  const active = !media.paused && !media.ended;
  const control = $('player-toggle');
  control.dataset.active = String(active);
  control.setAttribute('aria-label',active?'Pause':'Play');
  control.title = active?'Pause':'Play';
  const total = Number.isFinite(media.duration) ? media.duration : 0;
  $('elapsed').textContent = duration(media.currentTime);
  $('total-time').textContent = duration(total || (playing && playing.duration));
  const seek = $('seek');
  seek.max = total;
  seek.disabled = !total;
  seek.value = media.currentTime || 0;
  seek.setAttribute('aria-valuetext',$('elapsed').textContent+' of '+$('total-time').textContent);
}
for(const event of ['play','pause','ended','timeupdate','durationchange','emptied','loadedmetadata'])
  media.addEventListener(event,syncTransport);
$('seek').oninput = () => {
  if(Number.isFinite(media.duration)) media.currentTime = Math.min(media.duration,Number($('seek').value));
};
$('player-toggle').onclick = async () => {
  if(!media.paused) return media.pause();
  if(!media.getAttribute('src') || media.error) return playSong(playing);
  try { await media.play(); } catch(error) { toast(error.message); }
};
async function playSong(song,resume=false,automatic=false){
  const sequence=++playSequence, audio=$('audio');
  const position=resume&&!audio.ended?audio.currentTime:0;
  const paused=resume&&audio.paused;
  playing=song;$('player').hidden=false;$('player-title').textContent=song.title;$('player-artist').textContent=song.artist;
  document.body.classList.add('with-player');
  $('player-art').replaceChildren(art(song.image,song.title));
  $('player-toggle').disabled = true;
  $('player-status').textContent='Loading '+prefs.quality+' kbps audio…';
  audio.pause();
  audio.removeAttribute('src');
  audio.load();
  syncTransport();
  try{
    const data=await api('play',{key:song.key,quality:prefs.quality});
    if(sequence!==playSequence)return;
    audio.onloadedmetadata=()=>{if(sequence!==playSequence)return;if(position&&Number.isFinite(audio.duration))audio.currentTime=Math.min(position,Math.max(0,audio.duration-1));};
    audio.src=data.url;audio.load();
    $('player-status').textContent='';
    if(!paused){try{await audio.play();}catch(_){$('player-status').textContent='Tap the player’s play button to start audio.';}}
  }catch(error){if(sequence===playSequence){$('player-status').textContent=error.message;toast(error.message);}}
  finally { if(sequence===playSequence) $('player-toggle').disabled=false; }
}
$('audio').onerror=()=>{if(playing)$('player-status').textContent='Audio could not load. Try another quality or song.';};
$('player-quality').onchange=event=>saveSetting('quality',event.target.value);
$('close-player').onclick=()=>{++playSequence;playing=null;playbackQueue=[];queueIndex=-1;renderQueue();$('audio').pause();$('audio').removeAttribute('src');$('audio').load();$('player').hidden=true;document.body.classList.remove('with-player');};
const splashStarted=performance.now();
let splashDismissed=false;
function dismissSplash(){if(splashDismissed)return;splashDismissed=true;$('splash').classList.add('leaving');setTimeout(()=>$('splash').hidden=true,350);}
setTimeout(dismissSplash,4500);
async function init(){
  renderScreen();
  try{prefs=await api('settings');populateSettings();await Promise.all([poll(),loadDestination()]);}
  catch(error){message(error.message);}
  if(document.documentElement.classList.contains('native-startup')){
    $('splash').hidden=true;
    // Paint the real home screen behind the existing overlay before fading it.
    requestAnimationFrame(()=>requestAnimationFrame(()=>api('startup/ready',{}).catch(()=>{})));
  }else{
    const reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    setTimeout(dismissSplash,Math.max(0,(reduced?150:1450)-(performance.now()-splashStarted)));
  }
  setInterval(poll,1000);
}
init();
