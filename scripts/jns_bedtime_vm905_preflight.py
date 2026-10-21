#!/usr/bin/env python3
# Read-only HA-General bedtime inspection: native entities, labels, audio services.
import json,re
from pathlib import Path
root=Path('/config')
def load(n):
 try:return json.loads((root/'.storage'/n).read_text()).get('data',{})
 except Exception:return {}
labels={x.get('label_id'):x.get('name') for x in load('core.label_registry').get('labels',[])}
devices={x.get('id'):x for x in load('core.device_registry').get('devices',[])}
lines=['JNS Bedtime VM905 inventory (read-only)','Confirmed Z2M actions: 1_double / 1_hold','Westminster clock and soundscapes excluded.']
for x in load('core.entity_registry').get('entities',[]):
 eid=x.get('entity_id','')
 if not eid.startswith(('light.','switch.','media_player.','tts.','input_boolean.')):continue
 dev=devices.get(x.get('device_id'),{})
 labs=(x.get('labels') or [])+(dev.get('labels') or [])
 lines.append('ENTITY '+eid+' | '+str(x.get('name') or x.get('original_name') or '')[:60]+' | labels='+','.join(str(labels.get(v,v)) for v in labs))
for dev in devices.values():
 if 'ts0044' in str(dev).lower() or 'hallway 4 way' in str(dev).lower():
  lines.append('BUTTON DEVICE '+str(dev.get('name_by_user') or dev.get('name'))+' model '+str(dev.get('model')))
for x in load('core.config_entries').get('entries',[]):
 if x.get('domain') in ('tts','wyoming','piper','mpd'):lines.append('AUDIO INTEGRATION '+str(x.get('domain'))+' '+str(x.get('title',''))[:60])
for relative in ('configuration.yaml','automations.yaml','dashboards/testing.yaml'):
 p=root/relative
 if not p.exists():continue
 for n,s in enumerate(p.read_text(errors='replace').splitlines(),1):
  if re.search(r'bedtime|media_player\.|tts\.|wyoming|mpd',s,re.I):
   if not re.search(r'password|secret|token|key|http',s,re.I):
    lines.append(relative+':'+str(n)+' '+s.strip()[:150])
path=root/'jns_bedtime_preflight.txt'
path.write_text('\n'.join(lines)+'\n')
print('Saved '+str(path)+' ('+str(len(lines))+' lines)')
