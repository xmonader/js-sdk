from textwrap import dedent

from jumpscale.sals.chatflows.chatflows import chatflow_step
from jumpscale.sals.marketplace import MarketPlaceAppsChatflow, deployer, solutions
from jumpscale.loader import j
import nacl
from jumpscale.sals.reservation_chatflow import deployment_context, DeploymentFailed


class Discourse(MarketPlaceAppsChatflow):
    FLIST_URL = "https://hub.grid.tf/omar0.3bot/omarelawady-discourse-http.flist"
    SOLUTION_TYPE = "discourse"
    steps = [
        "get_solution_name",
        "discourse_smtp_info",
        "solution_expiration",
        "payment_currency",
        "infrastructure_setup",
        "reservation",
        "initializing",
        "success",
    ]

    title = "Discourse"
    query = {"cru": 1, "mru": 2, "sru": 2}

    @chatflow_step(title="SMTP information")
    def discourse_smtp_info(self):
        form = self.new_form()
        self.smtp_server = form.string_ask("SMTP server address", required=True)
        self.smtp_username = form.string_ask("SMTP server username", required=True)
        self.smtp_password = form.secret_ask("SMTP server password", required=True)
        form.ask()
        self.smtp_server = self.smtp_server.value
        self.smtp_username = self.smtp_username.value
        self.smtp_password = self.smtp_password.value
        self.user_email = self.user_info()["email"]
        self.username = self.user_info()["username"]

    @chatflow_step(title="Reservation", disable_previous=True)
    @deployment_context()
    def reservation(self):
        metadata = {
            "name": self.solution_name,
            "form_info": {"chatflow": self.SOLUTION_TYPE, "Solution name": self.solution_name},
        }
        self.solution_metadata.update(metadata)

        env = {
            "pub_key": "",
            "DISCOURSE_VERSION": "staging",
            "RAILS_ENV": "production",
            "DISCOURSE_HOSTNAME": self.domain,
            "DISCOURSE_SMTP_USER_NAME": self.smtp_username,
            "DISCOURSE_SMTP_ADDRESS": self.smtp_server,
            "DISCOURSE_DEVELOPER_EMAILS": self.user_email,
            "DISCOURSE_SMTP_PORT": "587",
            "THREEBOT_URL": "https://login.threefold.me",
            "OPEN_KYC_URL": "https://openkyc.live/verification/verify-sei",
            "UNICORN_BIND_ALL": "true",
        }
        threebot_private_key = nacl.signing.SigningKey.generate().encode(nacl.encoding.Base64Encoder).decode("utf-8")

        secret_env = {
            "THREEBOT_PRIVATE_KEY": threebot_private_key,
            "FLASK_SECRET_KEY": j.data.idgenerator.guid(),
            "DISCOURSE_SMTP_PASSWORD": self.smtp_password,
        }

        # reserve subdomain
        _id = deployer.create_subdomain(
            pool_id=self.pool_id,
            gateway_id=self.gateway.node_id,
            subdomain=self.domain,
            addresses=self.addresses,
            solution_uuid=self.solution_id,
            **self.solution_metadata,
        )

        success = deployer.wait_workload(_id, self)
        if not success:
            raise DeploymentFailed(
                f"Failed to create subdomain {self.domain} on gateway" f" {self.gateway.node_id} {_id}"
            )
        self.threebot_url = f"https://{self.domain}"

        entrypoint = f"/.start_discourse.sh"

        # reserve container
        self.resv_id = deployer.deploy_container(
            pool_id=self.pool_id,
            node_id=self.selected_node.node_id,
            network_name=self.network_view.name,
            ip_address=self.ip_address,
            flist=self.FLIST_URL,
            cpu=self.query["cru"],
            memory=self.query["mru"] * 1024,
            disk_size=self.query["sru"] * 1024,
            entrypoint=entrypoint,
            env=env,
            secret_env=secret_env,
            interactive=False,
            **self.solution_metadata,
            solution_uuid=self.solution_id,
        )
        success = deployer.wait_workload(self.resv_id, self)
        if not success:
            raise DeploymentFailed(f"Failed to deploy workload {self.resv_id}", solution_uuid=self.solution_id)

        _id = deployer.expose_and_create_certificate(
            pool_id=self.pool_id,
            gateway_id=self.gateway.node_id,
            network_name=self.network_view.name,
            trc_secret=self.secret,
            domain=self.domain,
            email=self.user_email,
            solution_ip=self.ip_address,
            solution_port=80,
            enforce_https=True,
            node_id=self.selected_node.node_id,
            solution_uuid=self.solution_id,
            proxy_pool_id=self.gateway_pool.pool_id,
            **self.solution_metadata,
        )
        success = deployer.wait_workload(_id, self)
        if not success:
            solutions.cancel_solution(self.username, self.workload_ids)
            raise DeploymentFailed(
                f"Failed to create trc container on node {self.selected_node.node_id} {_id}",
                solution_uuid=self.solution_id,
            )


chat = Discourse