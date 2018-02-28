import gevent


def test_close_event(
    generate_raiden_client,
    monitoring_service,
    get_random_bp
):
    monitoring_service.start()
    gevent.sleep(1)
    c1 = generate_raiden_client()
    c2 = generate_raiden_client()
    channel_address = c1.open_channel(c2.address)
    msg = get_random_bp(c1.address, c2.address, channel_address)

    monitoring_service.transport.send_message(msg)

    c1.close_channel(c2.address)
    gevent.sleep(1)
    assert channel_address not in monitoring_service.balance_proofs
