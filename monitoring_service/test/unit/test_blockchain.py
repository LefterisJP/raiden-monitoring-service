import gevent
from monitoring_service.constants import EVENT_CHANNEL_CLOSE
from monitoring_service.contract_manager import CONTRACT_MANAGER
from monitoring_service.utils import make_filter


# test if ChannelClosed event triggers an callback of the blockchain wrapper
class Trigger:
    def __init__(self):
        self.trigger_count = 0

    def trigger(self, *args):
        self.trigger_count += 1


def test_blockchain(generate_raiden_client, blockchain):

    t = Trigger()

    blockchain.register_handler(
        EVENT_CHANNEL_CLOSE,
        lambda ev: t.trigger()
    )
    blockchain.event_filter = blockchain.make_filter()
    blockchain.poll_interval = 0

    c1 = generate_raiden_client()
    c2 = generate_raiden_client()
    c1.open_channel(c2.address)
    c1.close_channel(c2.address)
    blockchain.poll_blockchain()

    assert t.trigger_count == 1


def test_filter(generate_raiden_client, web3):
    """test if filter returns past events"""
    c1 = generate_raiden_client()
    c2 = generate_raiden_client()
    c3 = generate_raiden_client()
    c1.open_channel(c2.address)
    c1.close_channel(c2.address)
    gevent.sleep(0)

    abi = CONTRACT_MANAGER.get_event_abi('NettingChannelContract', 'ChannelClosed')
    assert abi is not None
    f = make_filter(web3, abi[0], fromBlock=0)
    assert len(f.get_new_entries()) == 1
    c1.open_channel(c3.address)
    c1.close_channel(c3.address)
    assert len(f.get_new_entries()) == 1
    assert len(f.get_all_entries()) == 2
