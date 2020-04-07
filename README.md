# Exemplo de orquestrador Python para Watson Assistant

Inclui:

* Integração com Redis (IBM Cloud), para armazenamento de metadados sobre a sessão dos usuários com o Bot

* Integração com Facebook (via Webhook)

# IF DEPLOYING AT IKS (IBM Kubernetes Service):

## If you use the IBM-provided wildcard Ingress domain:

Get the IBM-provided TLS secret for your cluster.

``ibmcloud ks cluster get --cluster <cluster_name_or_ID> | grep Ingress``

Example output:

Ingress Subdomain:      mycluster-<hash>-0000.us-south.containers.appdomain.cloud

Ingress Secret:         mycluster-<hash>-0000

Edit the iks-config.yaml file.

## Setting up IBM Container Registry

Set Docker region
``ibmcloud cr region-set us-south``

Login to Docker
``ibmcloud cr login``

Destroy old images from IBM CR:
``ibmcloud cr image-rm <img_address>/<namespace>/<image_name>:<version>``

Build new container image and store at IBM CR:
``ibmcloud cr build -t <img_address>/<namespace>/<image_name>:<version> ./``

Destroy old deployment
``kubectl delete -f ./iks-config.yaml``

Create new deployment
``kubectl apply -f ./iks-config.yaml``
