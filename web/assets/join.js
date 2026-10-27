(() => {
  'use strict';
  const $ = (s) => document.querySelector(s);
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const params = new URLSearchParams(location.search);
  let payload = params.get('start') || '';
  if (!/^(o|r|e)_[A-Za-z0-9]{1,40}$/.test(payload)) payload = '';
  let eventId = null, role = '', name = '', experience = '';
  const chat = $('#chat');
  const bubble = (text, who='assistant') => { const el=document.createElement('div');el.className=`bubble ${who}`;el.textContent=text;chat.append(el);el.scrollIntoView({block:'nearest',behavior:'smooth'}); };
  const fail = (message) => { $('#error').textContent=message; };
  const api = async (url, options={}) => { const response=await fetch(url,{...options,cache:'no-store',headers:{Accept:'application/json',...(options.body?{'Content-Type':'application/json'}:{}),...options.headers}}); const data=await response.json().catch(()=>({}));if(!response.ok)throw new Error(data.detail||'Something went wrong. Please try again.');return data; };
  async function init(){
    try { const d=await api(`/api/join/resolve${payload?`?payload=${encodeURIComponent(payload)}`:''}`);eventId=d.event.id;$('#event-label').textContent=[d.event.name,d.event.city].filter(Boolean).join(' · ')||'Your event';if(d.kind==='community'&&d.community_name)$('#prompt').textContent=`You came in through ${d.community_name}. What will you bring to a team?`;if(payload)await api(`/api/join/click?payload=${encodeURIComponent(payload)}`,{method:'POST'}); }
    catch(e){fail(e.message);$('#roles').classList.add('hidden');}
  }
  $('#roles').addEventListener('click',e=>{const b=e.target.closest('[data-value]');if(!b)return;role=b.dataset.value;$('.choices').classList.add('hidden');bubble(b.textContent,'user');$('#name-step').classList.remove('hidden');$('#name').focus();});
  $('#name-form').addEventListener('submit',e=>{e.preventDefault();name=$('#name').value.trim();if(!name){$('#name').focus();return;}$('#name-step').classList.add('hidden');bubble(name,'user');$('#experience-step').classList.remove('hidden');});
  $('#experience-step').addEventListener('click',async e=>{const b=e.target.closest('[data-exp]');if(!b)return;experience=b.dataset.exp;$('#experience-step').classList.add('hidden');bubble(b.textContent,'user');await submit();});
  async function submit(){
    fail('');$('#loading').classList.remove('hidden');
    try {const p=await api('/api/join/register',{method:'POST',body:JSON.stringify({event_id:eventId,name,role,experience,language:'en',ref_payload:payload||null})});$('#loading').classList.add('hidden');
      const members=(p.team?.members||[]).map(m=>`<div class="team-member">${esc(m.first_name||'Teammate')} · ${esc(m.role_label||m.role||'Teammate')}</div>`).join('');
      const team=p.team_number?`<div class="team-card"><strong>Your team · ${esc(p.team_number)}</strong>${members||'<div class="team-member">You’re on the roster. More teammates can join soon.</div>'}</div>`:'<p>Your team assignment will appear as more people join.</p>';
      const invite=p.invite_link||location.href;const text=`I just joined ${p.event_name||'this hackathon'} on RadiUp.ai. Join my team: ${invite}`;const wa=`https://wa.me/?text=${encodeURIComponent(text)}`;
      $('#result').innerHTML=`<h2>You’re in, ${esc(p.name)}.</h2><p>We’ve added you to the team roster.</p>${team}<a class="invite-button" href="${esc(wa)}" target="_blank" rel="noopener noreferrer">Invite 2 teammates on WhatsApp ↗</a><p>Share this link with two people you’d like on your team.</p>`;$('#result').classList.remove('hidden');
    } catch(e){$('#loading').classList.add('hidden');fail(e.message);}
  }
  init();
})();
