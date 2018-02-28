from monitoring_service.utils import privkey_to_addr
from eth_utils import is_checksum_address
from monitoring_service.messages import BalanceProof


class MockRaidenNode:
    def __init__(self, privkey, channel_contract):
        self.privkey = privkey
        self.address = privkey_to_addr(privkey)
        self.contract = channel_contract
        self.channels = dict()
        self.netting_channel_abi = None
        self.web3 = self.contract.web3

    def open_channel(self, partner_address):
        assert is_checksum_address(partner_address)
        txid = self.contract.transact({'from': self.address}).newChannel(partner_address, 15)
        assert txid is not None
        c = self.contract.call({'from': self.address}).getChannelWith(partner_address)
        assert is_checksum_address(c)
        channel_contract = self.web3.eth.contract(abi=self.netting_channel_abi, address=c)
        self.channels[partner_address] = channel_contract
        return c

    def close_channel(self, partner_address):
        assert is_checksum_address(partner_address)
        assert partner_address in self.channels
        channel_contract = self.channels[partner_address]
        nonce = 0
        amount = 0
        locksroot = b'\x02'
        extra_hash = b'\x03'
        signature = bytes(64)
        channel_contract.transact({'from': self.address}).close(
            nonce, amount, locksroot, extra_hash, signature
        )

    def settle_channel(self, partner_address):
        assert is_checksum_address(partner_address)
        assert partner_address in self.channels
        channel_contract = self.channels[partner_address]
        channel_contract.transact({'from': self.address}).settle()

    def get_balance_proof(self, partner_address, value):
        assert partner_address in self.channels
        assert is_checksum_address(partner_address)
        channel_contract = self.channels[partner_address]
        return BalanceProof(
            channel_contract.address,
            self.address,
            partner_address
        )
