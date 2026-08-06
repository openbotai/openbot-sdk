# OpenBot SDK documentation

`openbot-sdk` is the open-source Python client for the OpenBot API.

> Current status: `0.0.2` source implementation complete; package unpublished;
> Hosted Data production remains `0.0.1` until its release gate passes.

## Start here

- [Getting started](getting-started.md): installation, authentication, Hosted
  Data client calls, pagination, cancellation, downloads, and errors.
- [API reference](api-reference.md): `Client`, Bench, Data resources, resource
  objects, webhooks, and exception types.
- [0.0.2 release contract](version-0.0.2.md): thin-client responsibility
  boundary and acceptance gates.
- [Runnable Data client flow](../examples/data_v002_workflow.py): public SDK example
  covered by mocked and opt-in live tests.

## Service boundary

The SDK implements the client contract; it does not provide the Hosted API.
Upload signing, authorization, R2 storage, job processing, review persistence,
artifact retention, and deletion enforcement are server responsibilities in the
main OpenBot repository.

The `0.0.2` client source can be tested against mocked endpoints. It must not be
reported as production-ready until the matching Hosted Data API is deployed and
the opt-in production smoke passes.
