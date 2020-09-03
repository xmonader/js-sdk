from nacl.encoding import Base64Encoder
from nacl.public import PrivateKey

from jumpscale.sals.chatflows.chatflows import chatflow_step
from jumpscale.sals.marketplace import MarketPlaceAppsChatflow, deployer
from jumpscale.loader import j
from jumpscale.sals.reservation_chatflow import deployment_context, DeploymentFailed


class TaigaDeploy(MarketPlaceAppsChatflow):
    FLIST_URL = "https://hub.grid.tf/waleedhammam.3bot/waleedhammam-taiga-latest.flist"
    SOLUTION_TYPE = "taiga"
    title = "Taiga"
    steps = [
        "get_solution_name",
        "taiga_credentials",
        "solution_expiration",
        "payment_currency",
        "infrastructure_setup",
        "overview",
        "reservation",
        "initializing",
        "success",
    ]

    query = {"cru": 1, "mru": 1, "sru": 4}

    @chatflow_step(title="Taiga Setup")
    def taiga_credentials(self):
        form = self.new_form()
        EMAIL_HOST_USER = form.string_ask("Please add the host email name for your solution.", required=True)
        EMAIL_HOST = form.string_ask(
            "Please add the smtp host example: `smtp.gmail.com`", default="smtp.gmail.com", required=True, md=True
        )
        EMAIL_HOST_PASSWORD = form.secret_ask("Please add the host email password", required=True)

        SECRET_KEY = form.secret_ask("Please add the secret for your solution", required=True)
        form.ask()
        self.EMAIL_HOST_USER = EMAIL_HOST_USER.value
        self.EMAIL_HOST = EMAIL_HOST.value
        self.EMAIL_HOST_PASSWORD = EMAIL_HOST_PASSWORD.value
        self.SECRET_KEY = SECRET_KEY.value
        self.user_email = self.user_info()["email"]
        self.username = self.user_info()["username"]

    @chatflow_step(title="Confirmation")
    def overview(self):
        self.metadata = {
            "Solution Name": self.solution_name,
            "Network": self.network_view.name,
            "Node ID": self.selected_node.node_id,
            "Pool": self.pool_id,
            "IP Address": self.ip_address,
            "Domain": self.domain,
        }
        self.md_show_confirm(self.metadata)

    @chatflow_step(title="Reservation", disable_previous=True)
    @deployment_context()
    def reservation(self):
        metadata = {
            "name": self.solution_name,
            "form_info": {"chatflow": self.SOLUTION_TYPE, "Solution name": self.solution_name},
        }
        self.solution_metadata.update(metadata)

        self.workload_ids = []

        # reserve subdomain
        subdomain_wid = self.workload_ids.append(
            deployer.create_subdomain(
                pool_id=self.pool_id,
                gateway_id=self.gateway.node_id,
                subdomain=self.domain,
                addresses=self.addresses,
                solution_uuid=self.solution_id,
                **self.solution_metadata,
            )
        )
        subdomain_wid = deployer.wait_workload(self.workload_ids[0], self)

        if not subdomain_wid:
            raise DeploymentFailed(
                f"Failed to create subdomain {self.domain} on gateway {self.gateway.node_id} {self.workload_ids[0]}"
            )

        private_key = PrivateKey.generate().encode(Base64Encoder).decode()
        flask_secret = j.data.idgenerator.chars(10)
        var_dict = {
            "EMAIL_HOST_USER": self.EMAIL_HOST_USER,
            "EMAIL_HOST": self.EMAIL_HOST,
            "TAIGA_HOSTNAME": self.domain,
            "HTTP_PORT": "80",
            "THREEBOT_URL": "https://login.threefold.me",
            "OPEN_KYC_URL": "https://openkyc.live/verification/verify-sei",
        }

        self.workload_ids.append(
            deployer.deploy_container(
                pool_id=self.pool_id,
                node_id=self.selected_node.node_id,
                network_name=self.network_view.name,
                ip_address=self.ip_address,
                flist=self.FLIST_URL,
                cpu=self.query["cru"],
                memory=self.query["mru"] * 1024,
                disk_size=self.query["sru"] * 1024,
                env=var_dict,
                interactive=False,
                entrypoint="/start_taiga.sh",
                public_ipv6=True,
                secret_env={
                    "EMAIL_HOST_PASSWORD": self.EMAIL_HOST_PASSWORD,
                    "PRIVATE_KEY": private_key,
                    "SECRET_KEY": self.SECRET_KEY,
                    "FLASK_SECRET_KEY": flask_secret,
                },
                **self.solution_metadata,
                solution_uuid=self.solution_id,
            )
        )
        success = deployer.wait_workload(self.workload_ids[-1], self)
        if not success:
            raise DeploymentFailed(f"Failed to deploy workload {self.workload_ids[-1]}", solution_uuid=self.solution_id)

        # expose threebot container
        self.workload_ids.append(
            deployer.expose_and_create_certificate(
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
        )
        success = deployer.wait_workload(self.workload_ids[-1], self)
        if not success:
            raise DeploymentFailed(
                f"Failed to create trc container on node {self.selected_node.node_id} {self.workload_ids[-1]}",
                solution_uuid=self.solution_id,
            )


chat = TaigaDeploy