import logging
import gevent
import sys
import traceback
from typing import List
from eth_utils import is_address

from monitoring_service.blockchain import BlockchainMonitor
from monitoring_service.state_db import StateDB
from monitoring_service.tasks import StoreBalanceProof
from monitoring_service.transport import Transport
from monitoring_service.constants import (
    EVENT_CHANNEL_CLOSE,
    EVENT_CHANNEL_SETTLED,
    EVENT_TRANSFER_UPDATED
)
from raiden_libs.messages import Message, BalanceProof
from raiden_libs.gevent_error_handler import register_error_handler
from raiden_libs.utils import private_key_to_address

from eth_utils import (
    is_checksum_address
)

log = logging.getLogger(__name__)


def order_participants(p1: str, p2: str):
    return (p1, p2) if p1 < p2 else (p2, p1)


def error_handler(context, exc_info):
    log.fatal("Unhandled exception terminating the program")
    traceback.print_exception(
        etype=exc_info[0],
        value=exc_info[1],
        tb=exc_info[2]
    )
    sys.exit()


class MonitoringService(gevent.Greenlet):
    def __init__(
        self,
        private_key: str,
        state_db: StateDB = None,
        transport: Transport = None,
        blockchain: BlockchainMonitor = None
    ) -> None:
        super().__init__()
        assert isinstance(private_key, str)
        assert isinstance(transport, Transport)
        assert isinstance(blockchain, BlockchainMonitor)
        assert isinstance(state_db, StateDB)
        self.private_key = private_key
        self.transport = transport
        self.blockchain = blockchain
        self.state_db = state_db
        self.stop_event = gevent.event.Event()
        assert is_checksum_address(private_key_to_address(self.private_key))
        self.transport.add_message_callback(lambda message: self.on_message_event(message))
        self.transport.privkey = lambda: self.private_key
        if state_db.is_initialized() is False:
            network_id = 6
            contract_address = '0xD5BE9a680AbbF01aB2d422035A64DB27ab01C624'
            receiver = private_key_to_address(private_key)
            state_db.setup_db(network_id, contract_address, receiver)
        self.task_list: List[gevent.Greenlet] = []

    def _run(self):
        register_error_handler(error_handler)
        self.transport.start()
        self.blockchain.start()
        self.blockchain.register_handler(
            EVENT_CHANNEL_CLOSE,
            lambda event, tx: self.on_channel_close(event, tx)
        )
        self.blockchain.register_handler(
            EVENT_CHANNEL_SETTLED,
            lambda event, tx: self.on_channel_settled(event, tx)
        )
        self.blockchain.register_handler(
            EVENT_TRANSFER_UPDATED,
            lambda event, tx: self.on_transfer_updated(event, tx)
        )

        # this loop will wait until spawned greenlets complete
        while self.stop_event.is_set() is False:
            tasks = gevent.wait(self.task_list, timeout=5, count=1)
            if len(tasks) == 0:
                gevent.sleep(5)
                continue
            task = tasks[0]
            self.task_list.remove(task)

    def stop(self):
        self.stop_event.set()

    def on_channel_close(self, event, tx):
        log.info('on channel close: event=%s tx=%s' % (event, tx))
        # check if we have balance proof for the closing
        closing_participant = event['args']['closing_participant']
        channel_id = event['args']['channel_identifier']
        assert is_address(closing_participant)
        assert channel_id > 0
        if channel_id not in self.state_db.balance_proofs:
            return
        balance_proof = self.state_db.balance_proofs[channel_id]
        if closing_participant not in (
            balance_proof['participant1'],
            balance_proof['participant2']
        ):
            log.warning('Event data do not match balance proof data! event=%s, bp=%s'
                        % (event, balance_proof))
            # TODO: remove balance proof?
            return

        # check if we should challenge closeChannel
        if self.check_event(event, balance_proof) is False:
            log.warning('Invalid balance proof submitted! Challenging! event=%s' % event)
            self.challenge_proof(channel_id)

    def on_channel_settled(self, event, tx):
        self.state_db.delete_balance_proof(event['args']['channel_identifier'])

    def on_transfer_updated(self, event, tx):
        log.warning('transferUpdated event! event=%s' % event)

    def check_event(self, event, balance_proof: BalanceProof):
        return False

    def challenge_proof(self, channel_id):
        balance_proof = self.state_db.balance_proofs.get(
            channel_id, None
        )
        log.info('challenging proof channel=%s BP=%s' % (channel_id, balance_proof))

    def on_message_event(self, message):
        """This handles messages received over the Transport"""
        assert isinstance(message, Message)
        if isinstance(message, BalanceProof):
            self.on_balance_proof(message)

    def on_balance_proof(self, balance_proof):
        """Called whenever a balance proof message is received.
        This will spawn a greenlet and store its reference in an internal list.
        Return value of the greenlet is then checked in the main loop."""
        assert isinstance(balance_proof, BalanceProof)
        task = StoreBalanceProof(self.blockchain.web3, self.state_db, balance_proof)
        task.start()
        self.task_list.append(task)

    @property
    def balance_proofs(self):
        return self.state_db.balance_proofs

    def wait_tasks(self):
        """Wait until all internal tasks are finished"""
        while True:
            if len(self.task_list) == 0:
                return
            gevent.sleep(1)
