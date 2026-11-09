// Lets `node --test` load the project's extensionless TypeScript imports ("./naf" -> "./naf.ts").
export async function resolve(specifier, context, next) {
  try {
    return await next(specifier, context);
  } catch (error) {
    if (specifier.startsWith(".") && !/\.\w+$/.test(specifier)) return next(specifier + ".ts", context);
    throw error;
  }
}
