const fs=require('node:fs');
const p=require('node:path').join(__dirname,'../frontend/src/main.jsx');
let s=fs.readFileSync(p,'utf8');
s=s.replace("{health?.mode==='live'?'真实模型模式':'规则演示模式'}","{health?.mode==='live'?(health.model+' · 真实模型'):'规则演示模式'}");
s=s.replace("{report&&<section className=\"panel report\">","{report&&state.mode==='live'&&<section className=\"panel agent-summary\"><div className=\"panel-title\"><h2>模型核验说明</h2><span>{health?.model} / 工具调用后的最终说明</span></div><details><summary>展开查看模型结论</summary><pre>{state.analysis}</pre></details><p className=\"muted\">以下比较表仍由确定性规则与计算生成，模型说明不会覆盖硬性条件。</p></section>}{report&&<section className=\"panel report\">");
fs.writeFileSync(p,s);
