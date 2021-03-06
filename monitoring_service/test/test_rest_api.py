import requests


def test_rest_api(monitoring_service, rest_api, generate_raiden_client):
    c1, c2 = generate_raiden_client(), generate_raiden_client()
    channel_id = c1.open_channel(c2.address)
    msg = c1.get_balance_proof(c2.address, transferred_amount=1, nonce=1)

    ret = requests.get('http://localhost:5001/api/1/balance_proofs')
    assert ret.json() == []
    monitoring_service.transport.send_message(msg)
    ret = requests.get('http://localhost:5001/api/1/balance_proofs')
    assert len([x for x in ret.json() if x['channel_id'] == channel_id]) == 1
