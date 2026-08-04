"""Anexos: CNH, RG, CRLV, contrato assinado — dado pessoal (LGPD).

`documents` é ponteiro polimórfico (`entity_type` + `entity_id`) e por isso NÃO tem foreign
key: nada cascateia. Excluir um motorista é soft delete. A soma das duas coisas deixava um
buraco silencioso: a listagem de anexos sumia da tela (a tela consulta por entidade) e o
`GET /files/{id}/download` continuava servindo o PDF da CNH pelo id do documento.

A tela dizia que o anexo tinha ido embora com o cadastro. O endpoint dizia o contrário.
"""

# PDF mínimo válido. O `_sniff` do `files/service.py` exige que os BYTES comecem com %PDF —
# não basta o `content-type` que o navegador manda pela extensão.
_PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< >>\n%%EOF\n"


def _subir(client, entity_type: str, entity_id: str, kind: str, nome: str = "documento.pdf"):
    return client.post(
        "/files/upload",
        data={"entity_type": entity_type, "entity_id": entity_id, "kind": kind},
        files={"file": (nome, _PDF, "application/pdf")},
    )


def test_cnh_de_motorista_excluido_deixa_de_ser_baixavel(auth_client, criar_motorista):
    """BUG REAL, corrigido nesta sessão. Direito de eliminação não pode depender de
    ninguém nunca descobrir o id do documento.

    Como falha se a guarda sumir: o último `assert` volta a receber 200 com os bytes da CNH.
    """
    motorista = criar_motorista()
    r = _subir(auth_client, "driver", motorista["id"], "cnh", "cnh.pdf")
    assert r.status_code == 201, r.text
    documento = r.json()

    # CONTROLE POSITIVO: baixava antes. Sem ele, um id inválido faria o teste passar sem
    # provar nada — o 404 do fim viria de "documento inexistente", não da regra.
    antes = auth_client.get(f"/files/{documento['id']}/download")
    assert antes.status_code == 200, antes.text
    assert antes.content == _PDF
    listagem = auth_client.get(
        "/files", params={"entity_type": "driver", "entity_id": motorista["id"]}
    )
    assert [d["id"] for d in listagem.json()] == [documento["id"]]

    assert auth_client.delete(f"/drivers/{motorista['id']}").status_code == 204

    # A tela some...
    assert (
        auth_client.get(
            "/files", params={"entity_type": "driver", "entity_id": motorista["id"]}
        ).status_code
        == 404
    )
    # ...e o arquivo some junto, que é o ponto.
    assert auth_client.get(f"/files/{documento['id']}/download").status_code == 404


def test_crlv_de_veiculo_excluido_deixa_de_ser_baixavel(auth_client, criar_veiculo):
    """A mesma regra pelo outro soft delete do sistema. Veículo tem nota fiscal de compra
    e laudo cautelar pendurados — documentos de valor, e o CRLV traz o nome do proprietário.
    """
    veiculo = criar_veiculo()
    documento = _subir(auth_client, "vehicle", veiculo["id"], "crlv", "crlv.pdf").json()

    assert auth_client.get(f"/files/{documento['id']}/download").status_code == 200

    assert auth_client.delete(f"/vehicles/{veiculo['id']}").status_code == 204

    assert auth_client.get(f"/files/{documento['id']}/download").status_code == 404


def test_o_anexo_dos_outros_continua_intacto(auth_client, criar_motorista):
    """CONTRAPROVA: a guarda tem que ser sobre o DONO do anexo, não sobre o endpoint.

    Sem este teste, "responder 404 para todo download" passaria nos dois testes acima.
    """
    excluido = criar_motorista()
    ativo = criar_motorista()
    doc_excluido = _subir(auth_client, "driver", excluido["id"], "cnh", "cnh.pdf").json()
    doc_ativo = _subir(auth_client, "driver", ativo["id"], "cnh", "cnh.pdf").json()

    assert auth_client.delete(f"/drivers/{excluido['id']}").status_code == 204

    assert auth_client.get(f"/files/{doc_excluido['id']}/download").status_code == 404
    assert auth_client.get(f"/files/{doc_ativo['id']}/download").status_code == 200
    listagem = auth_client.get(
        "/files", params={"entity_type": "driver", "entity_id": ativo["id"]}
    )
    assert [d["id"] for d in listagem.json()] == [doc_ativo["id"]]


def test_anexo_de_cadastro_excluido_ainda_pode_ser_apagado(auth_client, criar_motorista):
    """Bloquear a LEITURA não pode bloquear a ELIMINAÇÃO.

    Se o DELETE do documento também respondesse 404 depois de o motorista ser excluído, o
    PDF da CNH ficaria preso no storage para sempre, sem caminho pelo sistema para apagá-lo
    — o oposto exato do que a regra acima existe para garantir.
    """
    motorista = criar_motorista()
    documento = _subir(auth_client, "driver", motorista["id"], "cnh", "cnh.pdf").json()

    assert auth_client.delete(f"/drivers/{motorista['id']}").status_code == 204

    assert auth_client.delete(f"/files/{documento['id']}").status_code == 204
    # E some de verdade: agora é 404 por não existir mais, não por dono excluído.
    assert auth_client.get(f"/files/{documento['id']}/download").status_code == 404


def test_anexo_de_motorista_inexistente_e_recusado_no_upload(auth_client):
    """Regressão do que já funcionava: anexo órfão nunca entra."""
    r = _subir(auth_client, "driver", "00000000-0000-0000-0000-000000000000", "cnh")
    assert r.status_code == 404, r.text
