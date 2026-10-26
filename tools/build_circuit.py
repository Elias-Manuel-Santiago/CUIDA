"""Generate self-contained Fritzing breadboard project, custom parts, and preview.
Parts describe a virtual wiring model, not production PCB footprints.
"""
import csv
import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from html import escape

OUT = Path(__file__).resolve().parents[1] / 'circuit'
OUT.mkdir(parents=True, exist_ok=True)
PARTS = OUT / 'parts'
PARTS.mkdir(exist_ok=True)
SVGNS = 'http://www.w3.org/2000/svg'


def node(tag, parent=None, text=None, **attrs):
    el = ET.Element(tag, {k: str(v) for k, v in attrs.items()})
    if text is not None:
        el.text = text
    if parent is not None:
        parent.append(el)
    return el


def xml(el):
    return ET.tostring(el, encoding='utf-8', xml_declaration=True)


parts = {}
def part(key, title, pins, width, height, body, position, buses=None):
    # pins: list of (label, x, y), connector IDs remain stable by index.
    svg = node('svg', xmlns=SVGNS, width=f'{width/90}in', height=f'{height/90}in', viewBox=f'0 0 {width} {height}')
    g = node('g', svg, id='breadboard')
    # Body is authored SVG, not reused from Fritzing's graphic library.
    for child in ET.fromstring('<g>' + body + '</g>'):
        g.append(child)
    for i, (label, x, y) in enumerate(pins):
        node('circle', g, id=f'connector{i}pin', cx=x, cy=y, r=2.1,
             fill='#c8ab70' if key != 'breadboard' else '#404b55', stroke='#182f37', **{'stroke-width':'.4'})
    module = node('module', moduleId='cuida_' + key + '_v1', fritzingVersion='1.0.0')
    for tag, text in [('version', '1'), ('author', 'CUIDA prototype'), ('title', title),
                      ('label', key.upper()), ('date', '2026-10-25'),
                      ('description', 'Virtual prototype part. Mechanical dimensions and unused header positions are illustrative; not a fabrication footprint.')]:
        node(tag, module, text)
    props = node('properties', module)
    node('property', props, title, name='family')
    views = node('views', module)
    for view in ['breadboardView', 'iconView']:
        layers = node('layers', node(view, views), image=f'breadboard/cuida_{key}.svg')
        node('layer', layers, layerId='breadboard')
    connectors = node('connectors', module)
    for i, (label, _, _) in enumerate(pins):
        connector = node('connector', connectors, id=f'connector{i}', name=label, type='female' if key == 'breadboard' else 'male')
        node('description', connector, label)
        cv = node('views', connector)
        for view in ['breadboardView']:
            node('p', node(view, cv), layer='breadboard', svgId=f'connector{i}pin')
    if buses:
        bs = node('buses', module)
        for i, members in enumerate(buses):
            bus = node('bus', bs, id=f'bus{i}')
            for index in members:
                node('nodeMember', bus, connectorId=f'connector{index}')
    data = {'key': key, 'title': title, 'pins': pins, 'width': width, 'height': height,
            'svg': xml(svg), 'fzp': xml(module), 'position': position, 'buses': buses or [], 'index': len(parts)+1}
    parts[key] = data
    with zipfile.ZipFile(PARTS / f'{key}.fzpz', 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr(f'part.cuida_{key}.fzp', data['fzp'])
        z.writestr(f'svg.breadboard.cuida_{key}.svg', data['svg'])
    return data


pins, buses = [], []
body = '<rect x="0" y="0" width="612" height="216" rx="9" fill="#f1f2ef" stroke="#bcc4c4"/><rect x="12" y="94" width="588" height="13" rx="3" fill="#d6dcda"/>'
for column in range(63):
    for letter, y in zip('abcdefghij', [45,54,63,72,81,117,126,135,144,153]):
        pins.append((f'{letter}{column+1}',27+9*column,y))
    buses.extend([[column*10+r for r in range(5)], [column*10+r for r in range(5,10)]])
    if column % 5 == 4 or column == 0:
        body += f'<text x="{27+9*column}" y="38" font-size="6" text-anchor="middle" fill="#52616b">{column+1}</text>'
for rail, y, color in [('5V',18,'#c83232'), ('GND_TOP',27,'#26333b'), ('3V3',180,'#c67a0d'), ('GND_BOTTOM',189,'#26333b')]:
    indexes=[]
    for i in range(50):
        indexes.append(len(pins)); pins.append((f'{rail}_{i+1}',27+9*(i+i//5),y))
    buses.append(indexes)
    body += f'<path d="M18 {y-4} H594" stroke="{color}" stroke-width="1"/><text x="12" y="{y+2}" font-size="6" fill="{color}" text-anchor="end">{rail if rail in ("5V","3V3") else "-"}</text>'
bb = part('breadboard', 'Breadboard 830 contacts - continuous rail model', pins,612,216,body,(90,300),buses)

top = ['EN','VP','VN','34','35','32','33','25','26','27','14','12','13','GND_A','VIN']
bottom = ['23','22','TX0','RX0','21','19','18','5','17','16','4','2','15','GND_B','3V3']
epins = [(p,18+i*9,9) for i,p in enumerate(top)] + [(p,18+i*9,99) for i,p in enumerate(bottom)]
body='<rect x="1" y="1" width="160" height="106" rx="6" fill="#202d37" stroke="#0d1721"/><rect x="44" y="25" width="74" height="52" rx="3" fill="#b9c4ca"/><text x="81" y="49" font-size="10" text-anchor="middle" fill="#172d38">ESP32</text><text x="81" y="63" font-size="6" text-anchor="middle" fill="#172d38">DevKit V1 / 30 pins</text><rect x="0" y="43" width="14" height="22" fill="#becbd0"/>'
for i,p in enumerate(top): body+=f'<text x="{18+i*9}" y="20" font-size="4.7" fill="white" text-anchor="middle">{p.replace("_A","")}</text>'
for i,p in enumerate(bottom): body+=f'<text x="{18+i*9}" y="91" font-size="4.7" fill="white" text-anchor="middle">{p.replace("_B","")}</text>'
esp=part('esp32','ESP32 DevKit V1 - 30 pin wiring model',epins,162,108,body,(234,345))

def board_body(title, subtitle, color, width=144, height=90):
    return (f'<rect x="1" y="1" width="{width-2}" height="{height-2}" rx="5" fill="{color}" stroke="#153b3b"/>'
            f'<text x="{width/2}" y="29" font-size="12" text-anchor="middle" fill="white">{title}</text>'
            f'<text x="{width/2}" y="43" font-size="7" text-anchor="middle" fill="#d3e8e4">{subtitle}</text>')

mpins=[(p,18+i*18,72) for i,p in enumerate(['VCC','GND','SCL','SDA','AD0'])]
body=board_body('MPU6050','X forward / Y left / Z up','#166d78')
for p,x,y in mpins: body+=f'<text x="{x}" y="62" text-anchor="middle" font-size="7" fill="white">{p}</text>'
part('mpu6050','MPU6050 breakout - used pins',mpins,144,90,body,(465,150))
gpins=[(p,18+i*27,90) for i,p in enumerate(['VCC','GND','TX','RX'])]
body=board_body('GY-NEO6MV2','GPS / 9600 baud','#164f8c',144,108)
for p,x,y in gpins: body+=f'<text x="{x}" y="80" text-anchor="middle" font-size="8" fill="white">{p}</text>'
part('gps','GY-NEO6MV2 GPS breakout - illustrative header order',gpins,144,108,body,(465,600))
mpins=[(p,18+i*18,126) for i,p in enumerate(['VIN','GND','RXD','TXD'])]
body=board_body('A7670SA','5 V IN / 3.3 V UART assumed','#1b7652',162,144)
body+='<rect x="31" y="52" width="100" height="45" rx="3" fill="#b4c9c0"/><text x="81" y="78" text-anchor="middle" font-size="9" fill="#153c32">LTE Cat 1</text>'
for p,x,y in mpins: body+=f'<text x="{x}" y="116" text-anchor="middle" font-size="8" fill="white">{p}</text>'
part('modem','A7670SA carrier - simplified used-pin model',mpins,162,144,body,(810,300))
body=board_body('5 V / 2 A','regulated car adapter','#464667',144,90)
body+='<text x="36" y="63" font-size="8" text-anchor="middle" fill="white">+5V</text><text x="108" y="63" font-size="8" text-anchor="middle" fill="white">GND</text>'
part('power','Regulated 12V car adapter - 5V 2A output',[('5V',36,72),('GND',108,72)],144,90,body,(810,600))
body='<path d="M18 50 V72 M54 50 V72" stroke="#8d9aa3" stroke-width="2"/><rect x="12" y="3" width="48" height="54" rx="10" fill="#27456c"/><rect x="44" y="5" width="10" height="48" fill="#b3c4d7"/><text x="36" y="24" font-size="8" text-anchor="middle" fill="white">1000 uF</text><text x="36" y="36" font-size="7" text-anchor="middle" fill="white">10 V</text><text x="18" y="62" font-size="8">+</text><text x="54" y="62" font-size="8">-</text>'
part('capacitor','1000uF polarized capacitor - 10V minimum',[('+',18,72),('-',54,72)],72,81,body,(720,180))

def endpoint(key,label):
    p=parts[key]
    idx=next(i for i,x in enumerate(p['pins']) if x[0]==label)
    _,x,y=p['pins'][idx]; px,py=p['position']
    return (key,idx,px+x,py+y)

wires=[]
def wire(a,b,signal,color,bends=None):
    aa=endpoint(*a); bb=endpoint(*b)
    wires.append({'a':aa,'b':bb,'signal':signal,'color':color,'bends':bends or []})
def hole(label): return ('breadboard',label)
def ep(label): return ('esp32',label)

# Actual male headers inserted in the breadboard; direct connections, no jumper.
insertions=[]
for i,label in enumerate(top): insertions.append((endpoint('esp32',label),endpoint('breadboard',f'b{i+16}')))
for i,label in enumerate(bottom): insertions.append((endpoint('esp32',label),endpoint('breadboard',f'i{i+16}')))

wire(('power','5V'),hole('5V_1'),'5V','#cf363e',[(1020,672),(1020,290),(117,290)])
wire(('power','GND'),hole('GND_BOTTOM_45'),'GND','#344451',[(1038,672),(1038,540),(594,540)])
wire(hole('GND_TOP_1'),hole('GND_BOTTOM_1'),'GND','#344451',[(99,327),(99,489)])
wire(hole('5V_20'),hole('a30'),'5V','#cf363e')
wire(hole('GND_TOP_19'),hole('a29'),'GND','#344451')
wire(hole('j30'),hole('3V3_20'),'3V3','#c78612')
wire(hole('j29'),hole('GND_BOTTOM_20'),'GND','#344451')
wire(('mpu6050','VCC'),hole('3V3_35'),'3V3','#c78612',[(450,222),(450,555),(486,555)])
wire(('mpu6050','GND'),hole('GND_TOP_35'),'GND','#344451')
wire(('mpu6050','AD0'),hole('GND_TOP_36'),'GND','#344451')
wire(('mpu6050','SDA'),hole('j20'),'SDA GPIO21','#1a9a70',[(519,265),(420,265),(420,465)])
wire(('mpu6050','SCL'),hole('j17'),'SCL GPIO22','#327ccc',[(501,250),(408,250),(408,465)])
wire(('gps','VCC'),hole('5V_35'),'5V','#cf363e',[(438,690),(438,282),(486,282)])
wire(('gps','GND'),hole('GND_BOTTOM_35'),'GND','#344451')
wire(('gps','TX'),hole('a25'),'GPS TX to ESP RX27','#d38a19',[(537,735),(72,735),(72,270),(333,270)])
wire(('gps','RX'),hole('a24'),'ESP TX26 to GPS RX','#8b52bb',[(564,750),(54,750),(54,255),(324,255)])
wire(('modem','VIN'),hole('5V_45'),'5V','#cf363e',[(828,465),(783,465),(783,282),(594,282)])
wire(('modem','GND'),hole('GND_TOP_45'),'GND','#344451',[(846,447),(792,447),(792,273),(594,273)])
wire(('modem','TXD'),hole('j25'),'MODEM TX to ESP RX16','#d38a19',[(882,555),(333,555)])
wire(('modem','RXD'),hole('j24'),'ESP TX17 to MODEM RX','#8b52bb',[(864,570),(324,570)])
wire(('capacitor','+'),('modem','VIN'),'5V / capacitor +','#cf363e',[(738,270),(765,270),(765,480),(828,480)])
wire(('capacitor','-'),('modem','GND'),'GND / capacitor -','#344451',[(774,252),(774,492),(846,492)])

root=node('module',fritzingVersion='1.0.0',icon='')
node('title',root,'CUIDA virtual prototype v0.1')
views=node('views',root)
node('view',views,name='breadboardView',backgroundColor='#ffffff',gridSize='0.1in',showGrid='1',alignToGrid='1')
instances=node('instances',root)
iv={}
for key,p in parts.items():
    inst=node('instance',instances,moduleIdRef='cuida_'+key+'_v1',modelIndex=p['index'],path=f'cuida_{key}.fzp')
    node('title',inst,p['title'])
    view=node('breadboardView',node('views',inst),layer='breadboard')
    node('geometry',view,x=p['position'][0],y=p['position'][1],z=0 if key=='breadboard' else 2)
    iv[key]=node('connectors',view)

conn_nodes={}
def connect(key,index,target_index,target_connector,layer='breadboard'):
    identifier=(key,index)
    if identifier not in conn_nodes:
        c=node('connector',iv[key],connectorId=f'connector{index}',layer='breadboard')
        node('geometry',c,x=0,y=0)
        conn_nodes[identifier]=node('connects',c)
    node('connect',conn_nodes[identifier],modelIndex=target_index,connectorId=target_connector,layer=layer)
for a,b in insertions:
    connect(a[0],a[1],parts[b[0]]['index'],f'connector{b[1]}')
    connect(b[0],b[1],parts[a[0]]['index'],f'connector{a[1]}')

# Route each polyline as connected Fritzing wire segments, retaining electrical
# connectivity through both connector directions at bends.
wire_index=1000
for w in wires:
    a,b=w['a'],w['b']
    points=[(a[2],a[3])]+w['bends']+[(b[2],b[3])]
    ids=list(range(wire_index,wire_index+len(points)-1)); wire_index+=len(ids)
    connect(a[0],a[1],ids[0],'connector0','breadboardWire')
    connect(b[0],b[1],ids[-1],'connector1','breadboardWire')
    for j,(start,end) in enumerate(zip(points,points[1:])):
        index=ids[j]
        inst=node('instance',instances,moduleIdRef='WireModuleID',modelIndex=index,path='wire.fzp')
        node('title',inst,w['signal'])
        view=node('breadboardView',node('views',inst),layer='breadboardWire')
        node('geometry',view,x=start[0],y=start[1],z=4,x1=0,y1=0,x2=end[0]-start[0],y2=end[1]-start[1],wireFlags=64)
        node('wireExtras',view,mils='12',color=w['color'],opacity='1',banded='0')
        cs=node('connectors',view)
        for side in (0,1):
            c=node('connector',cs,connectorId=f'connector{side}',layer='breadboardWire')
            node('geometry',c,x=0,y=0)
            connections=node('connects',c)
            if side==0:
                target=(parts[a[0]]['index'],f'connector{a[1]}','breadboard') if j==0 else (ids[j-1],'connector1','breadboardWire')
            else:
                target=(parts[b[0]]['index'],f'connector{b[1]}','breadboard') if j==len(ids)-1 else (ids[j+1],'connector0','breadboardWire')
            node('connect',connections,modelIndex=target[0],connectorId=target[1],layer=target[2])

with zipfile.ZipFile(OUT/'CUIDA-v0.1.fzz','w',zipfile.ZIP_DEFLATED) as z:
    z.writestr('CUIDA-v0.1.fz',xml(root))
    for key,p in parts.items():
        z.writestr(f'part.cuida_{key}.fzp',p['fzp'])
        z.writestr(f'svg.breadboard.cuida_{key}.svg',p['svg'])

# Use the exact same SVG bodies, positions, and wiring for an inspectable preview.
preview=['<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="1100" viewBox="0 0 1100 865">',
 '<rect width="1100" height="865" fill="#f8fafb"/>',
 '<g font-family="Arial, sans-serif">',
 '<text x="48" y="45" font-size="27" font-weight="bold" fill="#142d40">CUIDA / Virtual breadboard prototype</text>',
 '<text x="48" y="73" font-size="13" fill="#536776">ESP32 + MPU6050 + GY-NEO6MV2 + A7670SA | v0.1</text>',
 '<text x="48" y="102" font-size="12" fill="#9a5f0d">ASSUMED: modem board VIN 5 V and UART 3.3 V; GPS breakout VCC 5 V / UART 3.3 V.</text>',
 '<text x="48" y="121" font-size="12" fill="#536776">Header order and board outlines are illustrative. Wire by labels, not by unverified hole positions.</text>']
for key,p in parts.items():
    svg=ET.fromstring(p['svg'])
    inner=''.join(ET.tostring(c,encoding='unicode') for c in svg)
    x,y=p['position']
    preview.append(f'<g transform="translate({x},{y})">{inner}</g>')
for w in wires:
    points=[(w['a'][2],w['a'][3])]+w['bends']+[(w['b'][2],w['b'][3])]
    ps=' '.join(f'{x},{y}' for x,y in points)
    preview.append(f'<polyline points="{ps}" fill="none" stroke="#ffffff" stroke-width="4" stroke-linejoin="round"/><polyline points="{ps}" fill="none" stroke="{w["color"]}" stroke-width="2" stroke-linejoin="round"/>')
preview += ['<text x="100" y="590" font-size="12" fill="#536776">Top rail: 5 V | Bottom positive rail: 3.3 V | Grounds bridged</text>',
 '<text x="48" y="790" font-size="12" fill="#142d40">Red: 5 V   Gold: 3.3 V   Dark: GND   Green/blue: I2C   Orange/purple: UART</text>',
 '<text x="48" y="814" font-size="12" fill="#536776">1000 uF capacitor across modem VIN/GND, not directly on bare-modem VBAT. No backup battery.</text>',
 '<text x="48" y="838" font-size="12" fill="#536776">Virtual wiring model: power transients, rail current capacity, RF and carrier compatibility are not simulated.</text>', '</g></svg>']
(OUT/'wiring-preview.svg').write_text(''.join(preview),encoding='utf-8')
with (OUT/'connections.csv').open('w',newline='',encoding='utf-8') as f:
    writer=csv.writer(f);writer.writerow(['From component','From pin','To component','To pin','Signal'])
    for w in wires:
        a,b=w['a'],w['b']
        writer.writerow([a[0],parts[a[0]]['pins'][a[1]][0],b[0],parts[b[0]]['pins'][b[1]][0],w['signal']])

netlist={'parts':{key:{k:v for k,v in p.items() if k not in ('svg','fzp')} for key,p in parts.items()},
         'insertions':insertions,'wires':wires}
(OUT/'netlist.json').write_text(json.dumps(netlist,indent=2),encoding='utf-8')
print('Generated editable Fritzing project, 7 bundled custom parts, connection list and SVG preview.')
