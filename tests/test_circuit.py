import json
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


class CircuitTests(unittest.TestCase):
    def test_power_and_signals_match_firmware_without_shorts(self):
        data=json.loads((ROOT/'circuit/netlist.json').read_text())
        parts=data['parts']
        parent={}
        def find(p):
            parent.setdefault(p,p)
            if parent[p]!=p: parent[p]=find(parent[p])
            return parent[p]
        def join(a,b): parent[find(a)]=find(b)
        def pin(key,label):
            return (key,next(i for i,x in enumerate(parts[key]['pins']) if x[0]==label))
        for key,p in parts.items():
            for bus in p['buses']:
                for i in bus: join((key,bus[0]),(key,i))
        for a,b in data['insertions']: join(tuple(a[:2]),tuple(b[:2]))
        for w in data['wires']: join(tuple(w['a'][:2]),tuple(w['b'][:2]))
        for labels in [
            [('power','5V'),('esp32','VIN'),('modem','VIN'),('gps','VCC'),('capacitor','+')],
            [('power','GND'),('esp32','GND_A'),('esp32','GND_B'),('modem','GND'),('gps','GND'),('mpu6050','GND'),('mpu6050','AD0'),('capacitor','-')],
            [('esp32','3V3'),('mpu6050','VCC')],
            [('esp32','21'),('mpu6050','SDA')],
            [('esp32','22'),('mpu6050','SCL')],
            [('esp32','27'),('gps','TX')],
            [('esp32','26'),('gps','RX')],
            [('esp32','16'),('modem','TXD')],
            [('esp32','17'),('modem','RXD')],
        ]:
            roots={find(pin(*p)) for p in labels}
            self.assertEqual(len(roots),1,labels)
        distinct=[('power','5V'),('power','GND'),('esp32','3V3'),('esp32','21'),('esp32','22'),('esp32','27'),('esp32','26'),('esp32','16'),('esp32','17')]
        self.assertEqual(len({find(pin(*p)) for p in distinct}),len(distinct))

    def test_fritzing_archive_references_and_reciprocity(self):
        with zipfile.ZipFile(ROOT/'circuit/CUIDA-v0.1.fzz') as z:
            sketch=ET.fromstring(z.read('CUIDA-v0.1.fz'))
            instances={x.get('modelIndex'):x for x in sketch.findall('./instances/instance')}
            definitions={}
            for name in z.namelist():
                if name.endswith('.fzp'):
                    part=ET.fromstring(z.read(name))
                    definitions[part.get('moduleId')]=part
                    svg=ET.fromstring(z.read('svg.breadboard.'+name[5:-4]+'.svg'))
                    ids={x.get('id') for x in svg.iter()}
                    for p in part.findall('.//connectors/connector/views/breadboardView/p'):
                        self.assertIn(p.get('svgId'),ids)
            for index,inst in instances.items():
                is_wire=inst.get('moduleIdRef')=='WireModuleID'
                if is_wire:
                    self.assertEqual(inst.find('./views/breadboardView/geometry').get('wireFlags'),'64')
                if not is_wire:
                    self.assertIn(inst.get('moduleIdRef'),definitions)
                for c in inst.findall('./views/breadboardView/connectors/connector'):
                    cid=c.get('connectorId')
                    for edge in c.findall('./connects/connect'):
                        target=instances[edge.get('modelIndex')]
                        candidates=target.findall('./views/breadboardView/connectors/connector')
                        reverse=[e for t in candidates if t.get('connectorId')==edge.get('connectorId')
                                 for e in t.findall('./connects/connect')
                                 if e.get('modelIndex')==index and e.get('connectorId')==cid]
                        self.assertTrue(reverse,(index,cid,edge.attrib))


if __name__=='__main__': unittest.main()
