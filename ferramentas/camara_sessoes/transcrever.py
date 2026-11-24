"""Sessões da Câmara de Cariacica: transcrição e resumo automáticos com o Gemini.

Lê o RSS do canal da Câmara no YouTube e, para cada sessão que ainda não tem arquivo em data/camara/sessoes/,
manda o vídeo ao Gemini em trechos de 40 minutos (só o áudio importa: poucos quadros e resolução baixa),
junta a transcrição com o horário do vídeo e pede um resumo estruturado: votações, falas sobre dinheiro
público, temas que o Vigia acompanha e momentos que servem para vídeo.

Uso:   python ferramentas/camara_sessoes/transcrever.py               (sessões novas, no máximo 3)
       python ferramentas/camara_sessoes/transcrever.py --video ID    (uma sessão específica)
       python ferramentas/camara_sessoes/transcrever.py --max 6
Precisa da variável GEMINI_API_KEY (segredo do GitHub). Modelo: GEMINI_MODEL (padrão: o gemini-X.Y-flash mais novo que a chave enxerga).

Regras: transcrição automática erra. Nenhuma frase vai a público sem conferir no vídeo, no minuto indicado.
Cidadão que fala na tribuna e não é agente público aparece como "Morador(a)", sem nome.
"""
import argparse, csv, datetime as dt, json, os, re, sys, time
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parents[2]
PASTA = RAIZ / 'data' / 'camara' / 'sessoes'
INDICE = RAIZ / 'data' / 'camara' / 'sessoes.csv'
CANAL = 'UCMRjwv3s47HO6kgU-Y5o-mQ'          # youtube.com/@camaramunicipaldecariacica3150
RSS = f'https://www.youtube.com/feeds/videos.xml?channel_id={CANAL}'
API = 'https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent'
MODELO = ['']                                 # modelo em uso (troca sozinho se o Google aposentar)
TRECHO = 20 * 60                              # segundos por chamada (40 min estourava o tempo de resposta)
MAX_TRECHOS = 18                              # 6 horas
COLUNAS = ['video_id', 'publicado', 'titulo', 'tipo', 'data_sessao', 'duracao_min', 'falas', 'modelo',
           'processado_em', 'arquivo']

P_TRANSCREVER = """Este é um trecho de uma sessão pública da Câmara Municipal de Cariacica (Espírito Santo).
Transcreva em português, palavra por palavra, toda a fala do trecho. Uma fala por linha, neste formato:
[mm:ss] Quem fala: texto
O horário é contado a partir do começo DESTE trecho (o primeiro segundo do trecho é [00:00]).
Quem fala: o nome do vereador, da vereadora ou do presidente quando for dito na sessão (por exemplo "com a
palavra o vereador Fulano"); se não der para saber, escreva "Vereador(a) não identificado(a)". Servidor ou
secretário municipal: nome e cargo, se forem ditos. Cidadão que não é agente público e fala na tribuna:
escreva "Morador(a)" e não escreva o nome dele.
Não resuma, não corrija a fala, não invente. Partes sem fala (música, intervalo, silêncio): uma linha
"[mm:ss] (sem fala)". Se o trecho estiver depois do fim do vídeo ou não tiver nenhuma fala, responda só: SEM_FALA"""

P_RESUMIR = """Abaixo está a transcrição automática de uma sessão da Câmara Municipal de Cariacica (ES), com o
horário do vídeo em cada fala. Faça um resumo fiel, só com o que está na transcrição (nada de fora, nada de
opinião). Responda só com JSON neste formato:
{"tipo": "ordinária|extraordinária|solene|especial|audiência|outra",
 "data_sessao": "AAAA-MM-DD ou vazio",
 "votacoes": [{"minuto": "hh:mm:ss", "projeto": "número e autor, se ditos", "assunto": "em linguagem simples",
               "resultado": "aprovado|rejeitado|adiado|retirado|não informado", "votos": "como foi dito"}],
 "dinheiro": [{"minuto": "hh:mm:ss", "quem": "", "resumo": "", "valor": "se foi dito", "citacao": "até 25 palavras, exatas"}],
 "temas": [{"tema": "saúde|PA do Trevo|obras|limpeza urbana|emergência|licitação|eventos|orçamento|educação|transporte|segurança|outro",
            "minuto": "hh:mm:ss", "quem": "", "resumo": ""}],
 "momentos_para_video": [{"minuto": "hh:mm:ss", "por_que": "", "citacao": "até 25 palavras, exatas"}],
 "presentes": [], "ausentes": []}
Use listas vazias quando não houver. "dinheiro" é toda fala sobre gasto, contrato, orçamento, crédito,
emenda, salário ou valor da prefeitura ou da Câmara. "momentos_para_video" são falas fortes e verificáveis
sobre o dinheiro ou os serviços da cidade (no máximo 8). Moradores não identificados aparecem como "Morador(a)"."""


def _get(url, **kw):
    r = requests.get(url, timeout=60, headers={'User-Agent': 'Mozilla/5.0 (vigia-cariacica)'}, **kw)
    r.raise_for_status()
    return r.text


def ler_rss():
    """Lista [{video_id, publicado, titulo}] do RSS, da mais nova para a mais antiga."""
    x = _get(RSS)
    out = []
    for e in x.split('<entry>')[1:]:
        vid = re.search(r'<yt:videoId>([^<]+)', e).group(1)
        pub = re.search(r'<published>([^<]+)', e).group(1)[:10]
        tit = re.search(r'<title>([^<]+)', e).group(1)
        out.append({'video_id': vid, 'publicado': pub, 'titulo': tit.replace('&amp;', '&').strip()})
    return out


def duracao_segundos(video_id):
    """Duração do vídeo: página do YouTube e, se ela vier sem o dado, a API interna do player.
    None quando nenhum dos dois responde (aí o trecho vazio encerra)."""
    try:
        h = _get(f'https://www.youtube.com/watch?v={video_id}&hl=pt')
        m = re.search(r'"lengthSeconds":"(\d+)"', h) or re.search(r'itemprop="duration" content="PT(\d+)M(\d+)S"', h)
        if m:
            return int(m.group(1)) if len(m.groups()) == 1 else int(m.group(1)) * 60 + int(m.group(2))
    except Exception:
        pass
    try:
        r = requests.post('https://www.youtube.com/youtubei/v1/player', timeout=60, json={
            'videoId': video_id, 'context': {'client': {'clientName': 'WEB', 'clientVersion': '2.20250101.00.00', 'hl': 'pt'}}})
        v = r.json().get('videoDetails', {}).get('lengthSeconds')
        return int(v) if v else None
    except Exception:
        return None


def data_do_titulo(titulo):
    m = re.search(r'\((\d{2})/(\d{2})/(\d{4})', titulo)
    return f'{m.group(3)}-{m.group(2)}-{m.group(1)}' if m else ''


def hms(seg):
    seg = int(round(seg))
    return f'{seg // 3600:02d}:{seg % 3600 // 60:02d}:{seg % 60:02d}'


def deslocar(texto, inicio):
    """Converte '[mm:ss]' ou '[h:mm:ss]' do trecho para o horário do vídeo inteiro ('[hh:mm:ss]')."""
    linhas = []
    for ln in texto.splitlines():
        m = re.match(r'\s*\[(\d{1,2}):(\d{2})(?::(\d{2}))?\]\s*(.*)', ln)
        if not m:
            if ln.strip() and linhas:
                linhas[-1] += ' ' + ln.strip()     # continuação da fala anterior
            continue
        a, b, c, resto = m.groups()
        seg = int(a) * 3600 + int(b) * 60 + int(c) if c else int(a) * 60 + int(b)
        linhas.append(f'[{hms(inicio + seg)}] {resto.strip()}')
    return linhas


def escolher_modelo(chave):
    """O Gemini aposenta modelos: escolhe o 'gemini-X.Y-flash' mais novo que a chave pode usar."""
    try:
        r = requests.get('https://generativelanguage.googleapis.com/v1beta/models?pageSize=200', timeout=60,
                         headers={'x-goog-api-key': chave})
        bons = []
        for m in r.json().get('models', []):
            nome = m.get('name', '').replace('models/', '')
            v = re.fullmatch(r'gemini-(\d+(?:\.\d+)?)-flash', nome)
            if v and 'generateContent' in m.get('supportedGenerationMethods', []):
                bons.append((float(v.group(1)), nome))
        if bons:
            return max(bons)[1]
    except Exception as e:
        print(f'  lista de modelos falhou: {e}', flush=True)
    return 'gemini-3.8-flash'


def gemini(partes, chave, modelo, json_saida=False, tentativas=4):
    corpo = {'contents': [{'role': 'user', 'parts': partes}],
             'generationConfig': {'temperature': 0.1, 'maxOutputTokens': 60000,
                                  'mediaResolution': 'MEDIA_RESOLUTION_LOW'}}
    if json_saida:
        corpo['generationConfig']['responseMimeType'] = 'application/json'
        del corpo['generationConfig']['mediaResolution']
    for t in range(tentativas):
        try:
            r = requests.post(API.format(modelo=modelo), json=corpo, timeout=(30, 1500),
                              headers={'x-goog-api-key': chave, 'Content-Type': 'application/json'})
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            espera = 30 * (t + 1)
            print(f'  Gemini sem resposta ({type(e).__name__}); nova tentativa em {espera} s', flush=True)
            time.sleep(espera)
            continue
        if r.status_code in (429, 500, 502, 503, 504):
            espera = 30 * (t + 1)
            print(f'  Gemini {r.status_code}; nova tentativa em {espera} s', flush=True)
            time.sleep(espera)
            continue
        if r.status_code == 404:
            m = re.search(r'use models/([a-z0-9.\-]+)', r.text)
            if m and m.group(1) != modelo:
                print(f'  modelo {modelo} aposentado; usando {m.group(1)}', flush=True)
                MODELO[0] = modelo = m.group(1)
                continue
        if r.status_code != 200:
            raise RuntimeError(f'Gemini {r.status_code}: {r.text[:500]}')
        j = r.json()
        cand = (j.get('candidates') or [{}])[0]
        texto = ''.join(p.get('text', '') for p in cand.get('content', {}).get('parts', []))
        return texto, cand.get('finishReason', ''), j.get('usageMetadata', {})
    raise RuntimeError('Gemini não respondeu depois de várias tentativas')


def transcrever(video_id, chave, modelo):
    dur = duracao_segundos(video_id)
    n = min(MAX_TRECHOS, -(-dur // TRECHO)) if dur else MAX_TRECHOS
    print(f'  duração: {hms(dur) if dur else "desconhecida"}; até {n} trecho(s)', flush=True)
    url = f'https://www.youtube.com/watch?v={video_id}'
    linhas, uso = [], 0
    for k in range(n):
        ini, fim = k * TRECHO, (k + 1) * TRECHO
        if dur:
            fim = min(fim, dur)
        partes = [{'fileData': {'fileUri': url, 'mimeType': 'video/*'},
                   'videoMetadata': {'startOffset': f'{ini}s', 'endOffset': f'{fim}s', 'fps': 0.1}},
                  {'text': P_TRANSCREVER}]
        try:
            texto, motivo, u = gemini(partes, chave, MODELO[0] or modelo)
        except RuntimeError as e:
            if not dur and k > 0 and '400' in str(e):
                break                                # passou do fim de um vídeo sem duração conhecida
            raise
        uso += int(u.get('totalTokenCount', 0))
        if texto.strip().upper().startswith('SEM_FALA'):
            if not dur:
                break
            continue
        novas = deslocar(texto, ini)
        if not dur and linhas and len(novas) < 3:
            break
        if motivo == 'MAX_TOKENS':
            novas.append(f'[{hms(fim)}] (aviso: transcrição deste trecho cortada pelo limite de saída)')
        linhas += novas
        print(f'  trecho {k + 1}: {hms(ini)}-{hms(fim)}, {len(novas)} falas', flush=True)
    return linhas, dur, uso


def resumir(linhas, titulo, chave, modelo):
    texto = f'Título do vídeo: {titulo}\n\n' + '\n'.join(linhas)
    saida, _, _ = gemini([{'text': P_RESUMIR + '\n\n' + texto}], chave, MODELO[0] or modelo, json_saida=True)
    try:
        return json.loads(saida)
    except json.JSONDecodeError:
        m = re.search(r'\{.*\}', saida, re.S)
        return json.loads(m.group(0)) if m else {'erro': 'resumo não veio em JSON', 'bruto': saida[:2000]}


def ler_indice():
    if not INDICE.exists():
        return {}
    with open(INDICE, newline='', encoding='utf-8') as f:
        return {r['video_id']: r for r in csv.DictReader(f)}


def gravar_indice(idx):
    INDICE.parent.mkdir(parents=True, exist_ok=True)
    linhas = sorted(idx.values(), key=lambda r: (r['data_sessao'] or r['publicado'], r['video_id']), reverse=True)
    with open(INDICE, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS)
        w.writeheader()
        w.writerows(linhas)


def processar(item, chave, modelo):
    vid, tit = item['video_id'], item['titulo']
    data = data_do_titulo(tit) or item['publicado']
    print(f'{data} {vid} {tit}', flush=True)
    linhas, dur, uso = transcrever(vid, chave, modelo)
    if not linhas:
        print('  sem fala transcrita; fica para a próxima execução', flush=True)
        return None
    resumo = resumir(linhas, tit, chave, modelo)
    PASTA.mkdir(parents=True, exist_ok=True)
    base = PASTA / f'{data}_{vid}'
    cab = [f'# {tit}', '', f'- Vídeo: https://www.youtube.com/watch?v={vid}',
           f'- Publicado no YouTube em {item["publicado"]}; duração {hms(dur) if dur else "não informada"}',
           f'- Transcrição automática ({modelo}, {dt.date.today().isoformat()}). Pode errar nomes e números: '
           'antes de citar em público, confira no vídeo, no minuto indicado.',
           '- Moradores que falam na tribuna aparecem como "Morador(a)", sem nome.', '', '## Transcrição', '']
    base.with_suffix('.md').write_text('\n'.join(cab + linhas) + '\n', encoding='utf-8')
    resumo.update({'video_id': vid, 'titulo': tit, 'publicado': item['publicado'], 'modelo': modelo,
                   'tokens': uso, 'aviso': 'Resumo automático da transcrição; conferir no vídeo antes de usar.'})
    base.with_suffix('.json').write_text(json.dumps(resumo, ensure_ascii=False, indent=1), encoding='utf-8')
    return {'video_id': vid, 'publicado': item['publicado'], 'titulo': tit, 'tipo': resumo.get('tipo', ''),
            # a data do título vale mais que a do resumo (em 11/11/2026 o modelo devolveu o ano 2022)
            'data_sessao': data_do_titulo(tit) or resumo.get('data_sessao') or data,'duracao_min': round(dur / 60) if dur else '',
            'falas': len(linhas), 'modelo': modelo, 'processado_em': dt.date.today().isoformat(),
            'arquivo': f'data/camara/sessoes/{base.name}.md'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--video', help='ID de um vídeo específico do canal')
    ap.add_argument('--max', type=int, default=3, help='sessões novas por execução')
    a = ap.parse_args()
    chave = os.environ.get('GEMINI_API_KEY', '').strip()
    if not chave:
        sys.exit('Falta o segredo GEMINI_API_KEY.')
    modelo = os.environ.get('GEMINI_MODEL', '').strip() or escolher_modelo(chave)
    MODELO[0] = modelo
    print(f'modelo: {modelo}', flush=True)
    idx = ler_indice()
    itens = ler_rss()
    if a.video:
        itens = [i for i in itens if i['video_id'] == a.video] or [{'video_id': a.video, 'publicado': '',
                                                                      'titulo': a.video}]
        idx.pop(a.video, None)
    fila = itens if a.video else [i for i in itens
                                  if i['video_id'] not in idx and re.search(r'sess|audi', i['titulo'], re.I)]
    print(f'{len(fila)} sessão(ões) nova(s); processando até {a.max}', flush=True)
    feitas = 0
    for item in fila[:a.max]:
        try:
            linha = processar(item, chave, modelo)
        except Exception as e:                      # uma sessão com erro não para as outras
            print(f'  ERRO: {e}', flush=True)
            continue
        if linha:
            idx[linha['video_id']] = linha
            gravar_indice(idx)
            feitas += 1
    print(f'{feitas} sessão(ões) transcrita(s)', flush=True)


if __name__ == '__main__':
    main()
