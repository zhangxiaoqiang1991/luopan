#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate self-contained HTML, Markdown and canonical JSON from one report model."""
import argparse, html, json, re
from pathlib import Path

REQ=("company","research_date","summary","sections","quiz_cards","sources")
HEALTH_LABELS={"complete":"完整","partial":"部分完整","missing":"缺失","conflict":"存在冲突","stale":"已过期","not_applicable":"不适用"}
AUDIENCE_LABELS={"investment":"投资者优先","career":"求职者优先","balanced":"投资与求职并重"}
def validate(m):
    missing=[x for x in REQ if x not in m]
    if missing: raise ValueError("missing: "+", ".join(missing))
    sources={x["id"] for x in m["sources"]}
    if "presentation" in m:
        p=m["presentation"]
        if p.get("primary_audience") not in {"investment","career","balanced"}: raise ValueError("invalid primary_audience")
        if p.get("secondary_policy") not in {"collapsed","expanded"}: raise ValueError("invalid secondary_policy")
        if not p.get("reason"): raise ValueError("presentation needs reason")
    allowed_health={"complete","partial","missing","conflict","stale","not_applicable"}
    for item in m.get("data_health",[]):
        if not all(k in item for k in ("dimension","status","obtained","required","notes")): raise ValueError("invalid data_health item")
        if item["status"] not in allowed_health: raise ValueError("invalid data_health status")
        if not isinstance(item["obtained"],int) or not isinstance(item["required"],int) or item["obtained"]<0 or item["required"]<0: raise ValueError("invalid data_health counts")
    fact_ids=set()
    for fact in m.get("facts",[]):
        if not all(k in fact for k in ("id","field","value","period","source_ids","confidence","is_inference","is_calculated")): raise ValueError("invalid fact core fields")
        if fact["id"] in fact_ids: raise ValueError("fact ids must be unique")
        fact_ids.add(fact["id"])
        if not isinstance(fact["source_ids"],list) or not set(fact["source_ids"])<=sources: raise ValueError("fact references unknown source")
        if not isinstance(fact["is_inference"],bool) or not isinstance(fact["is_calculated"],bool): raise ValueError("fact flags must be boolean")
        if fact["is_calculated"] and not fact.get("calculation"): raise ValueError("calculated fact needs calculation")
    for q in m["quiz_cards"]:
        choices={x["id"] for x in q.get("options",[])}; answers=set(q.get("correct_option_ids",[]))
        if q.get("type") not in ("single_choice","multiple_choice"): raise ValueError("quiz type must be single_choice/multiple_choice")
        if not choices or not answers or not answers<=choices: raise ValueError("invalid quiz choices")
        if q["type"]=="single_choice" and len(answers)!=1: raise ValueError("single quiz needs one answer")
        if q["type"]=="multiple_choice" and len(answers)<2: raise ValueError("multiple quiz needs two or more answers")
        if not set(q.get("evidence_ids",[]))<=sources: raise ValueError("unknown evidence")
    interview=m.get("interview_questions",[])
    if interview and len(interview)!=10: raise ValueError("interview_questions must contain exactly 10 questions")
    for q in interview:
        if not all(k in q for k in ("id","dimension","question","ask_to","green","yellow","red")): raise ValueError("invalid interview question")

def smap(m): return {x["id"]:x for x in m["sources"]}
def health_label(value): return HEALTH_LABELS.get(value,value)
def presentation(m):
    p=m.get("presentation",{})
    return p.get("primary_audience","balanced"),p.get("secondary_policy","collapsed")
def links(ids,s): return " · ".join(f'<a href="{html.escape(s[i]["url"],quote=True)}" target="_blank" rel="noopener">{html.escape(s[i]["title"])}</a>' for i in ids if i in s)
def body_html(value):
    paragraphs=[]
    for block in str(value).split('\n\n'):
        lines=[x.strip() for x in block.splitlines() if x.strip()]
        if not lines: continue
        if all(x.startswith(('- ','• ')) for x in lines):
            paragraphs.append('<ul>'+''.join(f'<li>{html.escape(x[2:])}</li>' for x in lines)+'</ul>')
        else:
            paragraphs.append('<p>'+ '<br>'.join(html.escape(x) for x in lines) +'</p>')
    return ''.join(paragraphs)

def render_markdown(m):
    s=smap(m); out=[f'# {m["company"]["name"]}公司调研报告','',f'- 研究日期：{m["research_date"]}',f'- 投资初筛：{m["summary"].get("investment","信息不足")}',f'- 求职初筛：{m["summary"].get("career","信息不足")}' ,'','## 先看结论','',m["summary"]["headline"],'']
    out += ['> **状态说明：** 通过（PASS）=该维度暂无否决性问题，不等于建议买入/入职；需关注（WARNING）=有重要风险待验证；不通过（FAIL）=该维度出现重大问题；证据不足（INSUFFICIENT）=当前信息不支持下结论。','']
    if m.get("data_health"):
        out += ['## 数据健康度','','| 维度 | 状态 | 已获取/必需 | 说明 |','|---|---|---:|---|']
        out += [f'| {x["dimension"]} | {health_label(x["status"])} | {x["obtained"]}/{x["required"]} | {x["notes"]} |' for x in m["data_health"]]; out += ['']
    if m.get("facts"):
        out += ['## 关键事实','','| 字段 | 值 | 期间 | 置信度 | 性质 |','|---|---|---|---|---|']
        for f in m["facts"]:
            nature='推断' if f["is_inference"] else ('计算' if f["is_calculated"] else '事实')
            value=f'{f["value"]} {f.get("currency",f.get("unit",""))}'.strip()
            out += [f'| {f["field"]} | {value} | {f["period"]} | {f["confidence"]} | {nature} |']
        out += ['']
    for sec in m["sections"]:
        out += [f'## {sec["title"]}','',sec["body"],'']
        refs=[s[x] for x in sec.get("evidence_ids",[]) if x in s]
        if refs: out += ['证据：'+'；'.join(f'[{x["title"]}]({x["url"]})' for x in refs),'']
    if m.get("interview_questions"):
        out += ['## 面试反问 10 问','', '> 不必一次问完。优先询问带★的问题，并向 HR、业务经理和未来同事交叉验证。','']
        for n,q in enumerate(m["interview_questions"],1):
            star='★ ' if q.get('priority') else ''
            out += [f'### {n}. {star}{q["dimension"]}','',f'**可直接问：** {q["question"]}','',f'**为什么这样问：** {q.get("why","")}','',f'**温和追问：** {q.get("follow_up","")}','',f'**优先询问：** {q["ask_to"]}','','> 以下信号仅供面试后复盘，不要当面展示。','','- 🟢 **绿灯：** '+q['green'],'- 🟡 **黄灯：** '+q['yellow'],'- 🔴 **红灯：** '+q['red'],'']
    out += ['<details>','<summary><strong>可选理解检查（选择题）</strong></summary>','', '> 可选练习，不影响完整报告的阅读。','']
    for n,q in enumerate(m["quiz_cards"],1):
        out += [f'### {n}. {q["question"]}（{"多选，可多选" if q["type"]=="multiple_choice" else "单选"}）','']+[f'- [ ] {o["id"]}. {o["text"]}' for o in q["options"]]
        refs='；'.join(f'[{s[x]["title"]}]({s[x]["url"]})' for x in q.get("evidence_ids",[]) if x in s)
        out += ['','<details>','<summary>查看答案与解析</summary>','',f'**答案：{"、".join(q["correct_option_ids"])}**','',q["explanation"],'']
        for oid, why in q.get("option_explanations",{}).items(): out += [f'- **{oid}：** {why}']
        if q.get("related_sections"): out += ['', '关联章节：'+'、'.join(q["related_sections"])]
        if refs: out += ['证据：'+refs,'']
        if q.get("follow_up_prompt"): out += ['可继续追问：`'+q["follow_up_prompt"]+'`','']
        out += ['</details>','']
    out += ['</details>','','## 来源','']+[f'- [{x["title"]}]({x["url"]})（{x.get("level","未分级")}）' for x in m["sources"]]
    return '\n'.join(out).rstrip()+'\n'

def render_html(m):
    s=smap(m); sections=[]; cards=[]; primary,secondary_policy=presentation(m)
    route_reason=m.get("presentation",{}).get("reason","")
    route_note=f'<p class=route-note>为什么采用这个视角：{html.escape(route_reason)}</p>' if route_reason else ''
    health=''
    if m.get('data_health'):
        rows=''.join(f'<tr><td>{html.escape(str(x["dimension"]))}</td><td><span class="health {html.escape(x["status"])}">{html.escape(health_label(x["status"]))}</span></td><td>{x["obtained"]}/{x["required"]}</td><td>{html.escape(str(x["notes"]))}</td></tr>' for x in m['data_health'])
        health=f'<section><h2>数据健康度</h2><div class=table-wrap><table><thead><tr><th>维度</th><th>状态</th><th>已获取/必需</th><th>说明</th></tr></thead><tbody>{rows}</tbody></table></div></section>'
    facts=''
    if m.get('facts'):
        rows=''.join(f'<tr><td>{html.escape(str(x["field"]))}</td><td>{html.escape(str(x["value"]))} {html.escape(str(x.get("currency",x.get("unit",""))))}</td><td>{html.escape(str(x["period"]))}</td><td>{html.escape(str(x["confidence"]))}</td><td>{"推断" if x["is_inference"] else ("计算" if x["is_calculated"] else "事实")}</td></tr>' for x in m['facts'])
        facts=f'<section><h2>关键事实</h2><div class=table-wrap><table><thead><tr><th>字段</th><th>值</th><th>期间</th><th>置信度</th><th>性质</th></tr></thead><tbody>{rows}</tbody></table></div></section>'
    for index,sec in enumerate(m["sections"]):
        ref=links(sec.get("evidence_ids",[]),s); body=body_html(sec["body"])
        content=f'<div>{body}</div>{f"<p class=refs>证据：{ref}</p>" if ref else ""}'
        audience=sec.get("audience","shared")
        is_secondary=(primary=="investment" and audience=="career") or (primary=="career" and audience=="investment")
        if index < 3 and not (secondary_policy=="collapsed" and is_secondary):
            sections.append(f'<section><h2>{html.escape(sec["title"])}</h2>{content}</section>')
        else:
            sections.append(f'<details class=deep><summary>{html.escape(sec["title"])}</summary>{content}</details>')
    for n,q in enumerate(m["quiz_cards"],1):
        typ='checkbox' if q["type"]=='multiple_choice' else 'radio'
        opts=''.join(f'<label class=option><input type={typ} name="{html.escape(q["id"])}" value="{html.escape(o["id"])}"><span><b>{html.escape(o["id"])}</b> {html.escape(o["text"])}</span></label>' for o in q["options"])
        ref=links(q.get("evidence_ids",[]),s); ans=html.escape(json.dumps(q["correct_option_ids"],ensure_ascii=False),quote=True)
        why=''.join(f'<li><b>{html.escape(k)}</b> {html.escape(v)}</li>' for k,v in q.get("option_explanations",{}).items())
        related='、'.join(q.get("related_sections",[])); prompt=html.escape(q.get("follow_up_prompt",''),quote=True)
        why_html=f'<ul>{why}</ul>' if why else ''; related_html=f'<p class=refs>关联章节：{html.escape(related)}</p>' if related else ''; ref_html=f'<p class=refs>证据：{ref}</p>' if ref else ''; follow_html=f'<button class=copy data-prompt="{prompt}">复制追问</button><span class=copied aria-live=polite></span>' if prompt else ''
        cards.append(f'<article class="quiz" data-answer="{ans}"><small>第 {n} 题 · {"多选（可多选）" if typ=="checkbox" else "单选"}</small><h3>{html.escape(q["question"])}</h3>{opts}<button class=submit>提交答案</button><div class=feedback hidden><strong></strong><p>{html.escape(q["explanation"])}</p>{why_html}{related_html}{ref_html}{follow_html}</div></article>')
    src=''.join(f'<li><a href="{html.escape(x["url"],quote=True)}">{html.escape(x["title"])}</a><span>{html.escape(x.get("level","未分级"))}</span></li>' for x in m["sources"])
    interview=''
    if m.get('interview_questions'):
        items=[]
        for n,q in enumerate(m['interview_questions'],1):
            star='<span class=must>优先必问</span>' if q.get('priority') else ''
            items.append(f'<article class=interview><small>{n}. {html.escape(q["dimension"])}</small>{star}<h3>{html.escape(q["question"])}</h3><p><b>为什么这样问：</b>{html.escape(q.get("why",""))}</p><p><b>温和追问：</b>{html.escape(q.get("follow_up",""))}</p><p class=askto>优先询问：{html.escape(q["ask_to"])}</p><details><summary>面试后复盘信号（勿当面展示）</summary><p><b>🟢 绿灯</b> {html.escape(q["green"])}</p><p><b>🟡 黄灯</b> {html.escape(q["yellow"])}</p><p><b>🔴 红灯</b> {html.escape(q["red"])}</p></details></article>')
        interview='<section><h2>面试反问 10 问</h2><p>不必一次问完。优先问标记的 3 题，并向 HR、业务经理和未来同事交叉验证。</p><div class=interview-grid>'+''.join(items)+'</div></section>'
    return f'''<!doctype html><html lang=zh-CN><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>{html.escape(m["company"]["name"])}公司调研</title><style>
:root{{--ink:#17202a;--paper:#f6f3ec;--card:#fff;--accent:#185c4d;--gold:#d5a53a;--bad:#9f3030}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.75 system-ui,"PingFang SC",sans-serif}}main{{max-width:1000px;margin:auto;padding:50px 24px}}header{{padding:44px;border-radius:24px;background:var(--ink);color:#fff}}h1{{font-size:clamp(36px,6vw,64px);margin:8px 0}}.headline{{color:#dce1e4;font-size:19px}}.chips{{display:flex;gap:8px;flex-wrap:wrap}}.chip{{border:1px solid #ffffff40;border-radius:99px;padding:6px 12px}}section,.quiz,.deep,.learning{{background:var(--card);border-radius:18px;padding:27px;margin:20px 0;box-shadow:0 8px 28px #17202a0b}}section>p,.deep>p{{margin:0 0 1em}}section>p:last-child,.deep>p:last-child{{margin-bottom:0}}.legend{{border-left:5px solid var(--gold)}}.legend-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}}.legend-grid p{{margin:0;padding:12px;border-radius:12px;background:#f7f7f4}}.deep summary,.learning>summary{{cursor:pointer;font-size:20px;font-weight:700}}.deep[open] summary,.learning[open]>summary{{margin-bottom:16px}}.grid,.interview-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}}.grid .quiz{{margin:0}}.interview{{border:1px solid #e3e6e2;border-radius:14px;padding:18px;background:#fbfcfa}}.interview h3{{font-size:17px;line-height:1.55}}.interview p{{margin:.65em 0}}.askto{{color:#68717d}}.must{{float:right;border-radius:99px;background:#fff0c9;color:#7d5b00;padding:2px 8px;font-size:12px}}small{{color:var(--gold)}}.option{{display:flex;gap:10px;border:1px solid #dde2df;border-radius:12px;padding:11px;margin:8px 0;cursor:pointer}}.option:has(input:checked){{background:#eaf4f0;border-color:var(--accent)}}button{{border:0;border-radius:10px;background:var(--accent);color:white;padding:11px 18px;cursor:pointer}}.feedback{{border-top:1px solid #eee;margin-top:15px;padding-top:12px}}.correct strong{{color:var(--accent)}}.wrong strong{{color:var(--bad)}}.refs{{font-size:13px;color:#68717d}}a{{color:var(--accent)}}section>ul li{{display:flex;justify-content:space-between;gap:12px}}.table-wrap{{overflow:auto}}table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;text-align:left;border-bottom:1px solid #e7e7e7}}.health{{border-radius:99px;padding:3px 8px;background:#eee}}.health.complete{{background:#dff2e8;color:#185c4d}}.health.missing,.health.conflict{{background:#f8dddd;color:#8b2929}}.health.stale,.health.partial{{background:#fff0c9;color:#7d5b00}}.health.not_applicable{{color:#68717d}}@media print{{body{{background:white}}button{{display:none}}.feedback{{display:block!important}}}}
</style></head><body><main><header><small>LUOPAN · COMPANY RESEARCH</small><h1>{html.escape(m["company"]["name"])}</h1><p class=headline>{html.escape(m["summary"]["headline"])}</p><div class=chips><span class=chip>{html.escape(m["research_date"])}</span><span class=chip>主视角：{html.escape(AUDIENCE_LABELS.get(primary,primary))}</span><span class=chip>投资：{html.escape(m["summary"].get("investment","信息不足"))}</span><span class=chip>求职：{html.escape(m["summary"].get("career","信息不足"))}</span></div>{route_note}</header><section class=legend><h2>状态怎么看</h2><div class=legend-grid><p><b>通过（PASS）</b><br>该维度暂无否决性问题。不等于建议买入或入职。</p><p><b>需关注（WARNING）</b><br>存在重要风险，需要继续验证。</p><p><b>不通过（FAIL）</b><br>该维度已出现重大问题。</p><p><b>证据不足（INSUFFICIENT）</b><br>当前信息不支持对该维度下结论。</p></div></section>{health}{facts}{''.join(sections)}{interview}<details class=learning><summary>可选理解检查（选择题）</summary><p>用于检查关键因果关系，不是使用门槛。</p><div class=grid>{''.join(cards)}</div></details><section><h2>来源</h2><ul>{src}</ul></section></main><script>document.querySelectorAll('.quiz .submit').forEach(b=>b.onclick=()=>{{let c=b.closest('.quiz'),a=JSON.parse(c.dataset.answer).sort(),v=[...c.querySelectorAll('input:checked')].map(x=>x.value).sort(),ok=a.length===v.length&&a.every((x,i)=>x===v[i]),f=c.querySelector('.feedback');f.hidden=false;f.className='feedback '+(ok?'correct':'wrong');f.querySelector('strong').textContent=ok?'回答正确':'还差一点，正确答案：'+a.join('、')}});document.querySelectorAll('.copy').forEach(b=>b.onclick=async()=>{{try{{await navigator.clipboard.writeText(b.dataset.prompt);b.nextElementSibling.textContent=' 已复制'}}catch(e){{b.nextElementSibling.textContent=' 复制失败，请手动复制：'+b.dataset.prompt}}}})</script></body></html>'''

def main():
    p=argparse.ArgumentParser(); p.add_argument('input',type=Path); p.add_argument('--output-dir',type=Path,required=True); a=p.parse_args(); m=json.loads(a.input.read_text(encoding='utf-8')); validate(m); a.output_dir.mkdir(parents=True,exist_ok=True)
    name=re.sub(r'[^\w\u4e00-\u9fff-]+','-',m['company']['name']).strip('-')+f'-公司调研-{m["research_date"]}'
    (a.output_dir/f'{name}.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); (a.output_dir/f'{name}.md').write_text(render_markdown(m),encoding='utf-8'); (a.output_dir/f'{name}.html').write_text(render_html(m),encoding='utf-8')
if __name__=='__main__': main()
