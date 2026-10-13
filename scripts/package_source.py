from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root=Path(__file__).resolve().parents[1]
destination=root.parent/'procure-agent-source.zip'
files=[]
for directory in ['backend','tests','scripts','frontend/src','frontend/public']:
    files.extend(p for p in (root/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
for name in ['README.md','PORTFOLIO.md','TEST_RESULTS.md','TEST_SUMMARY.json','LIVE_TEST_RESULTS.json','BOUNDARY_TEST_RESULTS.json','SOURCING_TEST_RESULTS.json','SOURCING_TEST_REPORT.md','requirements.txt','requirements.lock.txt','start.ps1','.env.example','.gitignore','frontend/package.json','frontend/package-lock.json','frontend/vite.config.js','frontend/index.html']:
    files.append(root/name)
with ZipFile(destination,'w',ZIP_DEFLATED) as archive:
    for file in files: archive.write(file,Path('procure-agent')/file.relative_to(root))
print(f'Packaged {len(files)} source files: {destination}')
