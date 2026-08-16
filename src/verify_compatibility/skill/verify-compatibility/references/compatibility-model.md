# Compatibility Model

## Dimensions

Treat compatibility as three independent dimensions.

1. **Conformance** checks the open format or repository declaration.
2. **Static portability** compares required behavior with reviewed target
   profiles.
3. **Runtime verification** records whether equivalent behavior was actually
   exercised on each target.

A parser success proves only that a client accepted input. It does not prove
that invocation, permissions, tools, authentication, sandbox behavior, or
outputs are equivalent.

## Static grades

- `portable`: no static gap was found.
- `portable-with-adapters`: a common core exists with explicit host adapters.
- `degraded`: at least one target loses or changes behavior.
- `incompatible`: at least one required capability is unavailable.
- `unverified`: documentation or declarations are insufficient.

## Evidence precedence

Use this order when evidence conflicts:

1. runtime evidence bound to the reviewed artifact and target version;
2. current official documentation for the exact target surface;
3. protocol or open-format specification;
4. repository implementation evidence;
5. model inference or community reports.

Lower-ranked evidence can identify a question, but must not silently override a
higher-ranked source.
